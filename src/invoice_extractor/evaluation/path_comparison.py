"""Paired comparison of the two ingestion paths (PRD 03 R5.2-R5.4; design D1, D10).

`compare_records` is a pure function of two saved run records, so a comparison can be re-rendered
without the model. `compare_paths` only produces the two records.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from invoice_extractor.client import ModelClient
from invoice_extractor.evaluation.execute import execute
from invoice_extractor.evaluation.manifest import Manifest
from invoice_extractor.evaluation.report import FieldLine, Rate, field_precision, rate
from invoice_extractor.evaluation.run_record import DocumentResult, IncompleteRunError, NoCallReason, RunRecord
from invoice_extractor.evaluation.stats import mcnemar_exact, percentile
from invoice_extractor.prompts import Prompt

SIGNIFICANCE = 0.05


class PathSummary(BaseModel):
    """One path over every headline document."""

    model_config = ConfigDict(frozen=True)

    path: str
    documents: int
    correct_outcome: Rate
    extraction_rate: Rate  # extractions over in-domain documents
    invented_values: int
    total_cost_usd: Decimal
    cost_usd_per_document: Decimal
    p95_latency_ms: int | None
    worst_field: str | None  # over the paired documents


class CoverageEntry(BaseModel):
    """A document path B cannot read: it measures coverage, not extraction quality (R5.3)."""

    model_config = ConfigDict(frozen=True)

    id: str
    tags: list[str]
    reason: NoCallReason
    path_a_classification: str


class FieldDelta(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    a: Rate
    b: Rate
    delta_points: float | None  # b minus a, in percentage points


class Verdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    winner: str  # "a", "b" or "tie"
    summary: str


class PathComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    documents: int
    a: PathSummary
    b: PathSummary
    coverage: list[CoverageEntry]
    # Paired over the documents both paths attempted (everything except the coverage group).
    paired_documents: int
    a_only_correct: int
    b_only_correct: int
    mcnemar_p: float
    # Per-field precision over the documents both paths extracted.
    both_extracted: int
    field_deltas: list[FieldDelta]
    verdict: Verdict


def _summary(path: str, results: list[DocumentResult], paired: list[DocumentResult]) -> PathSummary:
    in_domain = [r for r in results if r.entry.expected_outcome == "extracted"]
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    total = sum((r.cost_usd for r in results), Decimal(0))
    return PathSummary(
        path=path,
        documents=len(results),
        correct_outcome=rate(sum(_is_correct(r) for r in results), len(results)),
        extraction_rate=rate(sum(r.comparison.classification == "extraction" for r in in_domain), len(in_domain)),
        invented_values=sum(r.comparison.invented_values for r in results),
        total_cost_usd=total,
        cost_usd_per_document=total / len(results),
        p95_latency_ms=int(percentile(latencies, 0.95)) if latencies else None,
        worst_field=field_precision(paired).worst,
    )


def _is_correct(result: DocumentResult) -> bool:
    return result.comparison.classification in ("extraction", "correct_rejection")


def _headline_by_id(record: RunRecord, label: str) -> dict[str, DocumentResult]:
    if not record.config.complete:
        raise IncompleteRunError(f"path {label} run is incomplete; an incomplete run cannot be compared")
    return {r.entry.id: r for r in record.results if r.entry.source != "real"}


def compare_records(run_a: RunRecord, run_b: RunRecord) -> PathComparison:
    if (run_a.config.ingestion_path, run_b.config.ingestion_path) != ("a", "b"):
        raise ValueError("compare_records takes the path A run first and the path B run second")
    by_id_a, by_id_b = _headline_by_id(run_a, "A"), _headline_by_id(run_b, "B")
    if by_id_a.keys() != by_id_b.keys():
        raise ValueError("the two runs are not over the same documents, so they cannot be paired")
    if not by_id_a:
        raise ValueError("there are no documents to compare")

    ids = list(by_id_a)  # manifest order
    results_a, results_b = [by_id_a[i] for i in ids], [by_id_b[i] for i in ids]

    coverage = [
        CoverageEntry(
            id=i,
            tags=by_id_b[i].entry.tags,
            reason=by_id_b[i].no_call_reason,
            path_a_classification=by_id_a[i].comparison.classification,
        )
        for i in ids
        if by_id_b[i].no_call_reason is not None
    ]
    attempted = [i for i in ids if by_id_b[i].no_call_reason is None]
    a_only = sum(_is_correct(by_id_a[i]) and not _is_correct(by_id_b[i]) for i in attempted)
    b_only = sum(_is_correct(by_id_b[i]) and not _is_correct(by_id_a[i]) for i in attempted)

    both = [i for i in ids if by_id_a[i].comparison.classification == "extraction" == by_id_b[i].comparison.classification]
    paired_a, paired_b = [by_id_a[i] for i in both], [by_id_b[i] for i in both]
    lines_a, lines_b = field_precision(paired_a).fields, field_precision(paired_b).fields

    summary_a, summary_b = _summary("a", results_a, paired_a), _summary("b", results_b, paired_b)
    p_value = mcnemar_exact(a_only, b_only)
    return PathComparison(
        documents=len(ids),
        a=summary_a,
        b=summary_b,
        coverage=coverage,
        paired_documents=len(attempted),
        a_only_correct=a_only,
        b_only_correct=b_only,
        mcnemar_p=p_value,
        both_extracted=len(both),
        field_deltas=[_delta(line_a, line_b) for line_a, line_b in zip(lines_a, lines_b)],
        verdict=_verdict(summary_a, summary_b, len(coverage), p_value),
    )


def _delta(a: FieldLine, b: FieldLine) -> FieldDelta:
    both = a.rate.value is not None and b.rate.value is not None
    return FieldDelta(
        name=a.name, a=a.rate, b=b.rate, delta_points=float(b.rate.value - a.rate.value) * 100 if both else None
    )


def _verdict(a: PathSummary, b: PathSummary, unreadable: int, p_value: float) -> Verdict:
    """The winner is the path with more correct outcomes over all documents; a tie goes to the cheaper path.

    Reading every document is part of the domain, so coverage counts: a path that cannot read a
    document scores it as a failure. The trade-off is stated from the measured numbers.
    """
    k_a, k_b = a.correct_outcome.successes, b.correct_outcome.successes
    if k_a != k_b:
        winner = "a" if k_a > k_b else "b"
    elif a.cost_usd_per_document != b.cost_usd_per_document:
        winner = "a" if a.cost_usd_per_document < b.cost_usd_per_document else "b"
    else:
        winner = "tie"
    if winner == "tie":
        return Verdict(winner="tie", summary="The paths are indistinguishable on correct outcomes and on cost per document.")

    won, lost = (a, b) if winner == "a" else (b, a)
    n = a.documents
    parts = [
        f"Path {winner.upper()} wins: {won.correct_outcome.successes}/{n} correct outcomes against "
        f"{lost.correct_outcome.successes}/{n} for path {lost.path.upper()}.",
        f"Cost per document is ${won.cost_usd_per_document:.4f} against ${lost.cost_usd_per_document:.4f}.",
    ]
    if won.p95_latency_ms is not None and lost.p95_latency_ms is not None:
        parts.append(f"The p95 latency is {won.p95_latency_ms / 1000:.1f}s against {lost.p95_latency_ms / 1000:.1f}s.")
    if unreadable:
        parts.append(f"Path B cannot read {unreadable} of {n} documents (no text layer or an image), so it fails {'it' if unreadable == 1 else 'them'}.")
    significance = "distinguishable from noise" if p_value < SIGNIFICANCE else "within the noise"
    parts.append(f"On the documents both paths attempted the difference is {significance} (McNemar exact p = {p_value:.3f}).")
    return Verdict(winner=winner, summary=" ".join(parts))


async def compare_paths(
    manifest: Manifest,
    client: ModelClient,
    prompt: Prompt,
    *,
    max_concurrency: int,
    spend_cap_usd: Decimal,
) -> tuple[RunRecord, RunRecord | None]:
    """Run the same documents through path A and then path B; each run has its own spend cap.

    When the path A run is cut short by its cap, path B is not started (it would spend money on a
    comparison that cannot be made) and its record is `None`.
    """
    run_a = await execute(
        manifest, client, prompt, ingestion_path="a", max_concurrency=max_concurrency, spend_cap_usd=spend_cap_usd
    )
    if not run_a.config.complete:
        return run_a, None
    run_b = await execute(
        manifest, client, prompt, ingestion_path="b", max_concurrency=max_concurrency, spend_cap_usd=spend_cap_usd
    )
    return run_a, run_b


# --- rendering (ASCII only) ------------------------------------------------------------------------


def _docs(n: int) -> str:
    return f"{n} document" + ("" if n == 1 else "s")


def _pct(rate_: Rate) -> str:
    return "n/a" if rate_.n == 0 else f"{rate_.successes / rate_.n * 100:.1f}%"


def render_comparison_terminal(c: PathComparison) -> str:
    def row(label: str, a: str, b: str) -> str:
        return f"  {label:<26}{a:<24}{b}"

    lines = [
        f"INGESTION PATH COMPARISON  ({c.documents} documents; A = document/image block, B = local text)",
        row("", "path A", "path B"),
        row("correct outcome", f"{c.a.correct_outcome.successes}/{c.a.correct_outcome.n}  {_pct(c.a.correct_outcome)}",
            f"{c.b.correct_outcome.successes}/{c.b.correct_outcome.n}  {_pct(c.b.correct_outcome)}"),
        row("extraction rate", f"{c.a.extraction_rate.successes}/{c.a.extraction_rate.n}  {_pct(c.a.extraction_rate)}",
            f"{c.b.extraction_rate.successes}/{c.b.extraction_rate.n}  {_pct(c.b.extraction_rate)}"),
        row("invented values", str(c.a.invented_values), str(c.b.invented_values)),
        row("cost per document", f"${c.a.cost_usd_per_document:.4f}", f"${c.b.cost_usd_per_document:.4f}"),
        row("p95 latency", *[f"{s.p95_latency_ms / 1000:.1f}s" if s.p95_latency_ms is not None else "n/a" for s in (c.a, c.b)]),
        row("worst field (paired)", c.a.worst_field or "none", c.b.worst_field or "none"),
        "",
        f"COVERAGE  path B cannot read {_docs(len(c.coverage))} (kept out of the paired test):",
        *[f"  {e.id:<10}{e.reason:<16}path A: {e.path_a_classification}  tags: {', '.join(e.tags) or '-'}" for e in c.coverage],
        "",
        f"PAIRED  over the {_docs(c.paired_documents)} both paths attempted:",
        f"  only A correct {c.a_only_correct} | only B correct {c.b_only_correct} | McNemar exact p = {c.mcnemar_p:.3f}",
        "",
        f"FIELD DELTAS  (B minus A, in points, over the {_docs(c.both_extracted)} both paths extracted)",
        *[f"  {d.name:<26}{d.a.successes}/{d.a.n} -> {d.b.successes}/{d.b.n}   {d.delta_points:+.1f}"
          for d in c.field_deltas if d.delta_points not in (None, 0.0)],
        *(["  (no field differs)"] if not any(d.delta_points not in (None, 0.0) for d in c.field_deltas) else []),
        "",
        f"WINNER  path {c.verdict.winner.upper()}" if c.verdict.winner != "tie" else "WINNER  none (tie)",
        f"  {c.verdict.summary}",
    ]
    return "\n".join(lines) + "\n"


def render_comparison_markdown(c: PathComparison) -> str:
    lines = [
        "# Ingestion path comparison",
        "",
        f"{c.documents} documents. Path A sends the file as a document or image block; path B sends the text "
        "layer extracted locally with pdfplumber (no OCR).",
        "",
        "| | Path A | Path B |",
        "|---|---|---|",
        f"| Correct outcome | {c.a.correct_outcome.successes}/{c.a.correct_outcome.n} ({_pct(c.a.correct_outcome)}) "
        f"| {c.b.correct_outcome.successes}/{c.b.correct_outcome.n} ({_pct(c.b.correct_outcome)}) |",
        f"| Extraction rate | {c.a.extraction_rate.successes}/{c.a.extraction_rate.n} ({_pct(c.a.extraction_rate)}) "
        f"| {c.b.extraction_rate.successes}/{c.b.extraction_rate.n} ({_pct(c.b.extraction_rate)}) |",
        f"| Invented values | {c.a.invented_values} | {c.b.invented_values} |",
        f"| Cost per document | ${c.a.cost_usd_per_document:.4f} | ${c.b.cost_usd_per_document:.4f} |",
        "| p95 latency | " + " | ".join(
            f"{s.p95_latency_ms / 1000:.1f}s" if s.p95_latency_ms is not None else "n/a" for s in (c.a, c.b)) + " |",
        "",
        f"## Coverage: {_docs(len(c.coverage))} path B cannot read",
        "",
        "These measure coverage, not extraction quality, so they are kept out of the paired test.",
        "",
        "| Document | Why | Path A outcome | Tags |",
        "|---|---|---|---|",
        *[f"| {e.id} | {e.reason} | {e.path_a_classification} | {', '.join(e.tags) or '-'} |" for e in c.coverage],
        "",
        f"## Paired result ({_docs(c.paired_documents)} both paths attempted)",
        "",
        f"Only A correct: {c.a_only_correct}. Only B correct: {c.b_only_correct}. McNemar exact p = {c.mcnemar_p:.3f}.",
        "",
        f"## Field deltas (B minus A, points, over the {_docs(c.both_extracted)} both paths extracted)",
        "",
        "| Field | A | B | Delta |",
        "|---|---|---|---|",
        *[f"| `{d.name}` | {d.a.successes}/{d.a.n} | {d.b.successes}/{d.b.n} | "
          f"{'n/a' if d.delta_points is None else f'{d.delta_points:+.1f}'} |" for d in c.field_deltas],
        "",
        "## Winner",
        "",
        (f"**Path {c.verdict.winner.upper()}.** " if c.verdict.winner != "tie" else "**No winner.** ") + c.verdict.summary,
        "",
    ]
    return "\n".join(lines)
