"""The quality report: a pure function of a run record (PRD 03 R3, R1.2; design D1, D9).

Nothing here touches the network or the model. Documents whose manifest `source` is `real` are
split off before any number is computed, so they can never enter a headline count or rate (R3.5).
"""

from collections import Counter
from decimal import Decimal
from fractions import Fraction

from pydantic import BaseModel, ConfigDict

from invoice_extractor.evaluation.compare import INVOICE_LEAVES, INVOICE_LISTS
from invoice_extractor.evaluation.run_record import DocumentResult, IncompleteRunError, RunConfig, RunRecord
from invoice_extractor.evaluation.stats import percentile, wilson_interval

NO_TAG = "(no tag)"
_LIST_NAMES = tuple(INVOICE_LISTS)


class Rate(BaseModel):
    """k out of n, with its 95% Wilson interval. No interval for n = 0 or when the sample is too small to have one."""

    model_config = ConfigDict(frozen=True)

    successes: int
    n: int
    low: float | None
    high: float | None

    @property
    def value(self) -> Fraction | None:
        return Fraction(self.successes, self.n) if self.n else None


def rate(successes: int, n: int, *, interval: bool = True) -> Rate:
    low, high = wilson_interval(successes, n) if interval and n else (None, None)
    return Rate(successes=successes, n=n, low=low, high=high)


class FieldLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    rate: Rate
    extra_entries: int | None = None  # only on `<list>_per_entry` lines


class FieldPrecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    extractions: int  # the denominator N: in-domain documents whose actual outcome is `extracted`
    fields: list[FieldLine]
    worst: str | None


class Outcomes(BaseModel):
    model_config = ConfigDict(frozen=True)

    documents: int
    in_domain: int
    negatives: int
    correct_outcome: Rate
    extraction_rate: Rate
    false_rejections: int
    correct_rejections: int
    reason_agreement: Rate  # informative, not scored (R3.4)
    false_acceptances: int
    invented_values: int
    missed_values: int


class TagLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    tag: str
    documents: int
    correct_outcome: Rate
    perfect_extractions: Rate  # extractions with every field correct and every list exact


class Cost(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_usd: Decimal
    mean_usd_per_document: Decimal  # over every document, so a free explicit failure lowers the mean


class Latency(BaseModel):
    model_config = ConfigDict(frozen=True)

    p50_ms: int
    p95_ms: int


class Headline(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcomes: Outcomes
    fields: FieldPrecision
    by_tag: list[TagLine]
    attempts: dict[int, int]
    cost: Cost
    latency: Latency | None  # over documents that made a call


class RealSet(BaseModel):
    """The separate real-set section: same field-precision shape, no intervals, never a headline number."""

    model_config = ConfigDict(frozen=True)

    documents: int
    extractions: int
    false_rejections: int
    fields: FieldPrecision
    cost_usd: Decimal


class Report(BaseModel):
    model_config = ConfigDict(frozen=True)

    config: RunConfig
    headline: Headline | None
    real: RealSet | None


# --- computation ---------------------------------------------------------------------------------


def _extractions(results: list[DocumentResult]) -> list[DocumentResult]:
    return [r for r in results if r.comparison.classification == "extraction"]


def _is_perfect(result: DocumentResult) -> bool:
    comparison = result.comparison
    return all(f.status == "correct" for f in comparison.fields) and all(l.exact for l in comparison.lists)


def field_precision(results: list[DocumentResult], *, interval: bool = True) -> FieldPrecision:
    """Per-field precision over the successful extractions among `results` (measurement-rules §2, §3)."""
    extractions = _extractions(results)
    n = len(extractions)
    lines: list[FieldLine] = []

    correct_by_field = Counter(f.path for r in extractions for f in r.comparison.fields if f.status == "correct")
    for leaf in INVOICE_LEAVES:
        lines.append(FieldLine(name=leaf.path, rate=rate(correct_by_field[leaf.path], n, interval=interval)))

    for name in _LIST_NAMES:
        list_results = [next(l for l in r.comparison.lists if l.name == name) for r in extractions]
        entries = sum(l.expected_count for l in list_results)
        lines.append(FieldLine(name=f"{name}_exact", rate=rate(sum(l.exact for l in list_results), n, interval=interval)))
        lines.append(
            FieldLine(
                name=f"{name}_per_entry",
                rate=rate(sum(l.correct_entries for l in list_results), entries, interval=interval),
                extra_entries=sum(l.extra_entries for l in list_results),
            )
        )
    return FieldPrecision(extractions=n, fields=lines, worst=_worst(lines))


def _worst(lines: list[FieldLine]) -> str | None:
    """Lowest precision among the scalar fields and the per-entry list lines; ties are broken by name.

    The `<list>_exact` lines are left out: they are document-level composites of many fields, so they
    would nearly always be the lowest and say nothing about which field is weak (design D9). When
    every scored field is at 100% there is no worst field, so nothing is marked.
    """
    candidates = [
        line for line in lines if not line.name.endswith("_exact") and line.rate.value is not None
    ]
    if not candidates:
        return None
    worst = min(candidates, key=lambda line: (line.rate.value, line.name))
    return worst.name if worst.rate.value < 1 else None


def _outcomes(results: list[DocumentResult]) -> Outcomes:
    counts = Counter(r.comparison.classification for r in results)
    in_domain = sum(r.entry.expected_outcome == "extracted" for r in results)
    rejections = [r for r in results if r.comparison.classification == "correct_rejection"]
    return Outcomes(
        documents=len(results),
        in_domain=in_domain,
        negatives=len(results) - in_domain,
        correct_outcome=rate(counts["extraction"] + counts["correct_rejection"], len(results)),
        extraction_rate=rate(counts["extraction"], in_domain),
        false_rejections=counts["false_rejection"],
        correct_rejections=counts["correct_rejection"],
        reason_agreement=rate(sum(bool(r.comparison.reason_agrees) for r in rejections), len(rejections)),
        false_acceptances=counts["false_acceptance"],
        invented_values=sum(r.comparison.invented_values for r in results),
        missed_values=sum(r.comparison.missed_values for r in results),
    )


def _by_tag(results: list[DocumentResult]) -> list[TagLine]:
    tags = sorted({tag for r in results for tag in r.entry.tags})
    lines = []
    for tag in [*tags, NO_TAG]:
        group = [r for r in results if (tag in r.entry.tags if tag != NO_TAG else not r.entry.tags)]
        if not group:
            continue
        extractions = _extractions(group)
        lines.append(
            TagLine(
                tag=tag,
                documents=len(group),
                correct_outcome=rate(
                    sum(r.comparison.classification in ("extraction", "correct_rejection") for r in group), len(group)
                ),
                perfect_extractions=rate(sum(_is_perfect(r) for r in extractions), len(extractions)),
            )
        )
    return lines


def _headline(results: list[DocumentResult]) -> Headline:
    total = sum((r.cost_usd for r in results), Decimal(0))
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    return Headline(
        outcomes=_outcomes(results),
        fields=field_precision(results),
        by_tag=_by_tag(results),
        attempts=dict(sorted(Counter(r.attempts for r in results).items())),
        cost=Cost(total_usd=total, mean_usd_per_document=total / len(results)),
        latency=(
            Latency(p50_ms=int(percentile(latencies, 0.5)), p95_ms=int(percentile(latencies, 0.95)))
            if latencies
            else None
        ),
    )


def build_report(record: RunRecord) -> Report:
    """Compute every report section from a saved run record. Never calls the model."""
    if not record.config.complete:
        raise IncompleteRunError(
            "this run was stopped by its spend cap and is incomplete; an incomplete run is never reported as a result"
        )
    synthetic = [r for r in record.results if r.entry.source != "real"]
    real = [r for r in record.results if r.entry.source == "real"]
    return Report(
        config=record.config,
        headline=_headline(synthetic) if synthetic else None,
        real=(
            RealSet(
                documents=len(real),
                extractions=len(_extractions(real)),
                false_rejections=sum(r.comparison.classification == "false_rejection" for r in real),
                fields=field_precision(real, interval=False),
                cost_usd=sum((r.cost_usd for r in real), Decimal(0)),
            )
            if real
            else None
        ),
    )


# --- rendering (ASCII only: Windows consoles cannot print the arrows and dots of the PRD sketch) -----


def _percent(value: float) -> str:
    return f"{value * 100:.1f}"


def _interval(r: Rate) -> str:
    return f"[{_percent(r.low)}, {_percent(r.high)}]" if r.low is not None else ""


def _stat(r: Rate) -> str:
    """`k/n`, the percentage and the interval, in fixed columns."""
    counts = f"{r.successes}/{r.n}"
    if r.n == 0:
        return f"{counts:<9}{'n/a':>7}"
    return f"{counts:<9}{_percent(r.successes / r.n):>6}%  {_interval(r)}".rstrip()


def _run_line(config: RunConfig) -> str:
    sha = (config.git_sha or "nogit")[:7] + (" dirty" if config.git_dirty else "")
    stamp = config.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{config.model_id} | prompt {config.prompt_version} | path {config.ingestion_path} | {sha} | {stamp}"


def _seconds(ms: int) -> str:
    return f"{ms / 1000:.1f}s"


def _worst_text(fields: FieldPrecision) -> str:
    if fields.worst:
        return fields.worst
    return "none (every scored field is correct)" if fields.extractions else "n/a (nothing was extracted)"


def _field_rows(fields: FieldPrecision) -> list[str]:
    rows = []
    for line in fields.fields:
        text = f"  {line.name:<26}{_stat(line.rate)}"
        if line.extra_entries is not None:
            text += f"  (extra entries {line.extra_entries})"
        if line.name == fields.worst:
            text += "   <- worst field"
        rows.append(text)
    return rows


def render_terminal(report: Report) -> str:
    lines = [f"{'RUN':<21}{_run_line(report.config)}"]
    headline = report.headline
    if headline is not None:
        o = headline.outcomes
        lines += [
            f"{'DOCUMENTS':<21}{o.documents}   (in-domain {o.in_domain} | negatives {o.negatives})",
            f"{'Correct outcome':<21}{_stat(o.correct_outcome)}",
            f"{'  extraction rate':<21}{_stat(o.extraction_rate)}   of in-domain",
            f"{'  false rejections':<21}{o.false_rejections}",
            f"{'  correct rejections':<21}{o.correct_rejections}",
            f"{'    reason agreement':<21}{_stat(o.reason_agreement)}   informative, not scored",
            f"{'  false acceptances':<21}{o.false_acceptances}",
            f"{'Invented values':<21}{o.invented_values}",
            f"{'Missed values':<21}{o.missed_values}",
            "",
            f"FIELD PRECISION  (over successful extractions: {headline.fields.extractions})",
            f"  {'':<26}{'n/N':<9}{'%':>7}  95% CI",
            *_field_rows(headline.fields),
            f"Worst field          {_worst_text(headline.fields)}",
            "",
            "BY TAG               (documents | correct outcome | perfect extractions)",
            *[
                f"  {t.tag:<24}{t.documents:<4}{_stat(t.correct_outcome)}   perfect {_stat(t.perfect_extractions)}"
                for t in headline.by_tag
            ],
            "",
            f"{'ATTEMPTS':<21}" + " | ".join(f"{k}: {headline.attempts.get(k, 0)}" for k in sorted({1, 2, 3, *headline.attempts})),
            f"{'COST':<21}total ${headline.cost.total_usd:.4f} | mean ${headline.cost.mean_usd_per_document:.4f}/doc   (measured from usage)",
            f"{'LATENCY':<21}"
            + (
                f"p50 {_seconds(headline.latency.p50_ms)} | p95 {_seconds(headline.latency.p95_ms)}   (wall clock per document)"
                if headline.latency
                else "n/a (no document made a call)"
            ),
        ]
    real = report.real
    if real is not None:
        lines += [
            "",
            f"REAL SET  ({real.documents} documents)  NOT a headline number: too small for a confidence interval,",
            "                     and never mixed into any number above",
            f"  extractions {real.extractions}/{real.documents} | false rejections {real.false_rejections} | cost ${real.cost_usd:.4f}",
            f"  FIELD PRECISION  (over successful extractions: {real.fields.extractions})",
            *_field_rows(real.fields),
        ]
    return "\n".join(lines) + "\n"


def _md_stat(r: Rate) -> str:
    if r.n == 0:
        return f"0/0 | n/a | "
    return f"{r.successes}/{r.n} | {_percent(r.successes / r.n)}% | {_interval(r)}"


def _md_fields(fields: FieldPrecision) -> list[str]:
    rows = ["| Field | n/N | % | 95% CI | |", "|---|---|---|---|---|"]
    for line in fields.fields:
        note = []
        if line.extra_entries is not None:
            note.append(f"extra entries {line.extra_entries}")
        if line.name == fields.worst:
            note.append("**worst field**")
        rows.append(f"| `{line.name}` | {_md_stat(line.rate)} | {', '.join(note)} |")
    return rows


def render_markdown(report: Report) -> str:
    lines = ["# Quality report", "", f"Run: {_run_line(report.config)}", ""]
    headline = report.headline
    if headline is not None:
        o = headline.outcomes
        lines += [
            "## Documents",
            "",
            f"{o.documents} documents (in-domain {o.in_domain}, negatives {o.negatives}).",
            "",
            "| Measure | n | % | 95% CI | |",
            "|---|---|---|---|---|",
            f"| Correct outcome | {_md_stat(o.correct_outcome)} | |",
            f"| Extraction rate (of in-domain) | {_md_stat(o.extraction_rate)} | |",
            f"| Reason agreement (correct rejections) | {_md_stat(o.reason_agreement)} | informative, not scored |",
            "",
            f"False rejections: {o.false_rejections}. Correct rejections: {o.correct_rejections}. "
            f"False acceptances: {o.false_acceptances}. Invented values: {o.invented_values}. "
            f"Missed values: {o.missed_values}.",
            "",
            f"## Field precision (over successful extractions: {headline.fields.extractions})",
            "",
            *_md_fields(headline.fields),
            "",
            f"Worst field: `{headline.fields.worst}`" if headline.fields.worst else f"Worst field: {_worst_text(headline.fields)}",
            "",
            "## By tag",
            "",
            "| Tag | Documents | Correct outcome | 95% CI | Perfect extractions | 95% CI |",
            "|---|---|---|---|---|---|",
            *[
                f"| {t.tag} | {t.documents} | {t.correct_outcome.successes}/{t.correct_outcome.n} "
                f"| {_interval(t.correct_outcome)} | {t.perfect_extractions.successes}/{t.perfect_extractions.n} "
                f"| {_interval(t.perfect_extractions)} |"
                for t in headline.by_tag
            ],
            "",
            "## Attempts, cost and latency",
            "",
            "Attempts: " + ", ".join(f"{k}: {headline.attempts.get(k, 0)}" for k in sorted({1, 2, 3, *headline.attempts})),
            "",
            f"Cost (measured from usage): total ${headline.cost.total_usd:.4f}, "
            f"mean ${headline.cost.mean_usd_per_document:.4f} per document.",
            "",
            (
                f"Latency (wall clock per document): p50 {_seconds(headline.latency.p50_ms)}, "
                f"p95 {_seconds(headline.latency.p95_ms)}."
                if headline.latency
                else "Latency: n/a (no document made a call)."
            ),
            "",
        ]
    real = report.real
    if real is not None:
        lines += [
            f"## Real set ({real.documents} documents)",
            "",
            "**Not a headline number.** Too small for a confidence interval, and never mixed into any number above.",
            "",
            f"Extractions {real.extractions}/{real.documents}, false rejections {real.false_rejections}, "
            f"cost ${real.cost_usd:.4f}.",
            "",
            f"Field precision (over successful extractions: {real.fields.extractions}):",
            "",
            *_md_fields(real.fields),
            "",
        ]
    return "\n".join(lines)
