"""Builders for evaluation tests: documents, extraction records, results and run records, all API-free."""

import copy
import json
from datetime import UTC, datetime
from decimal import Decimal

from invoice_extractor.client import CallFailure, CallRecord, Parsed
from invoice_extractor.evaluation.compare import compare
from invoice_extractor.evaluation.manifest import SYNTHETIC_DIR, DocumentEntry
from invoice_extractor.evaluation.run_record import DocumentResult, RunConfig, RunRecord, aggregate
from invoice_extractor.extraction import ExtractionRecord
from invoice_extractor.schema import Extracted, ExtractionResult, Invoice


def truth_payload(document: str = "A01") -> dict:
    """The ground-truth invoice of a synthetic document as a JSON-decoded dict; safe to mutate."""
    payload = json.loads((SYNTHETIC_DIR / f"{document}.json").read_text(encoding="utf-8"))
    return copy.deepcopy(payload["result"]["invoice"])


def extracted(invoice: dict) -> ExtractionResult:
    return ExtractionResult.model_validate({"result": {"outcome": "extracted", "invoice": invoice}})


def failed(reason: str = "not_an_invoice") -> ExtractionResult:
    return ExtractionResult.model_validate({"result": {"outcome": "failed", "reason": reason, "detail": "n/a"}})


def make_entry(
    doc_id: str = "A01",
    *,
    source: str = "synthetic",
    tags: tuple[str, ...] = (),
    expected_outcome: str = "extracted",
    expected_reason: str | None = None,
    fmt: str = "pdf",
) -> DocumentEntry:
    return DocumentEntry(
        id=doc_id,
        file=f"{doc_id}.{fmt}",
        format=fmt,
        source=source,
        tags=list(tags),
        expected_outcome=expected_outcome,
        expected_reason=expected_reason,
        generator_version=None if source == "real" else {"git_sha": "f7ff2e1"},
    )


def make_call(
    outcome: ExtractionResult | CallFailure,
    *,
    cost: str = "0.010",
    latency_ms: int = 1_000,
    input_tokens: int = 5_000,
    output_tokens: int = 2_000,
) -> CallRecord[ExtractionResult]:
    wrapped = outcome if isinstance(outcome, CallFailure) else Parsed[ExtractionResult](value=outcome)
    return CallRecord[ExtractionResult](
        outcome=wrapped,
        model_id="claude-sonnet-5",
        stop_reason=None if isinstance(outcome, CallFailure) else "end_turn",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        latency_ms=latency_ms,
        cost_usd=Decimal(cost),
        request_id=None,
    )


def make_result(
    entry: DocumentEntry,
    prediction: ExtractionResult | CallFailure | None,
    truth: Invoice | None = None,
    **call_kwargs,
) -> DocumentResult:
    """One scored document. `prediction=None` is a document that ended without any model call."""
    if prediction is None:
        return DocumentResult(
            entry=entry,
            extraction=None,
            no_call_reason="image_input" if entry.format == "jpg" else "no_text_layer",  # as path B decides it
            attempts=0,
            comparison=compare(None, truth, entry.expected_outcome, entry.expected_reason),
        )
    call = make_call(prediction, **call_kwargs)
    model_result = prediction if isinstance(prediction, ExtractionResult) else None
    return DocumentResult(
        entry=entry,
        extraction=ExtractionRecord(source=entry.file, prompt_version="v1", call=call),
        no_call_reason=None,
        attempts=1,
        comparison=compare(model_result, truth, entry.expected_outcome, entry.expected_reason),
    )


def perfect_result(entry: DocumentEntry, **call_kwargs) -> DocumentResult:
    """An in-domain document extracted exactly as its ground truth says."""
    invoice = truth_payload(entry.id)
    return make_result(entry, extracted(invoice), Invoice.model_validate(invoice), **call_kwargs)


def make_config(**overrides) -> RunConfig:
    values = dict(
        model_id="claude-sonnet-5",
        prompt_version="v1",
        schema_hash="0" * 64,
        anthropic_version="1.5.0",
        pydantic_version="2.12.0",
        ingestion_path="a",
        generator_version={"git_sha": "f7ff2e1"},
        git_sha="b8bc5d4" + "0" * 33,
        git_dirty=False,
        timestamp=datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC),
        max_concurrency=3,
        spend_cap_usd=Decimal("1.00"),
        complete=True,
    )
    values.update(overrides)
    return RunConfig(**values)


def make_record(results: list[DocumentResult], **config_overrides) -> RunRecord:
    return RunRecord(config=make_config(**config_overrides), aggregates=aggregate(results), results=results)


def is_extracted(result: ExtractionResult) -> bool:
    return isinstance(result.result, Extracted)


def write_dataset(directory, documents: list[tuple[str, str]], *, source: str = "synthetic"):
    """Write a tiny dataset (fake PDFs, ground truth, manifest) and return its manifest.

    `documents` is (id, kind) with kind "extracted" (ground truth is the A01 invoice) or "negative"
    (a not_an_invoice failure). Each PDF's bytes embed its id so a fake SDK can tell documents apart.
    """
    from invoice_extractor.evaluation.manifest import load_manifest

    lines = []
    for doc_id, kind in documents:
        entry = make_entry(
            doc_id,
            expected_outcome="extracted" if kind == "extracted" else "explicit_failure",
            expected_reason=None if kind == "extracted" else "not_an_invoice",
            source=source,
        )
        (directory / entry.file).write_bytes(b"%PDF-1.4\n% " + doc_id.encode())
        truth = (
            {"result": {"outcome": "extracted", "invoice": truth_payload("A01")}}
            if kind == "extracted"
            else {"result": {"outcome": "failed", "reason": "not_an_invoice", "detail": "n/a"}}
        )
        (directory / f"{doc_id}.json").write_text(json.dumps(truth), encoding="utf-8")
        lines.append(entry.model_dump_json())
    (directory / "manifest.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return load_manifest(directory)
