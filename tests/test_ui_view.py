"""The UI's own logic, tested without Streamlit and without an API key (PRD 06 R7.1)."""

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from builders import extracted, failed, make_call, truth_payload
from invoice_extractor.client import CallFailure
from invoice_extractor.extraction import ExtractionRecord
from invoice_extractor.ui import view


def record(outcome, *, source: str = "B01.pdf", **call_kwargs) -> ExtractionRecord:
    return ExtractionRecord(source=source, prompt_version="v1", call=make_call(outcome, **call_kwargs))


# --- rows -----------------------------------------------------------------------------------------


def test_extracted_invoice_row_carries_its_type_and_numbers():
    row = view.row_from_record(record(extracted(truth_payload("B01")), cost="0.0376", latency_ms=12_300))

    assert (row.outcome, row.invoice_type, row.label) == ("extracted", "B", "Factura B")
    assert row.is_success
    assert (row.cost_usd, row.input_tokens, row.output_tokens, row.latency_ms) == (
        Decimal("0.0376"), 5_000, 2_000, 12_300,
    )
    assert row.currency == "ARS" and row.total > 0 and row.issuer
    assert row.attempts == 1


def test_model_failure_row_has_the_reason_and_no_invoice_fields():
    row = view.row_from_record(record(failed("not_an_invoice"), source="remito.pdf"))

    assert (row.outcome, row.reason, row.label) == ("model_failure", "not_an_invoice", "No es una factura")
    assert not row.is_success
    assert (row.invoice_type, row.total, row.issuer) == (None, None, None)
    assert row.cost_usd == Decimal("0.010")  # a refused document still cost a call


def test_call_failure_row_has_the_kind():
    row = view.row_from_record(record(CallFailure(kind="truncated", detail="stop_reason=max_tokens")))

    assert row.outcome == "call_failure"
    assert row.reason == "truncated"
    assert "cortada" in row.label
    assert not row.is_success


def test_not_processed_row_has_no_numbers():
    row = view.not_processed_row("huge.pdf", "se alcanzó el tope de gasto de la sesión ($1.00)")

    assert (row.outcome, row.label) == ("not_processed", "No procesado")
    assert (row.cost_usd, row.latency_ms, row.attempts) == (Decimal(0), None, 0)


def test_invoice_of_returns_the_invoice_only_for_an_extraction():
    assert view.invoice_of(record(extracted(truth_payload("A01")))) is not None
    assert view.invoice_of(record(failed())) is None
    assert view.invoice_of(record(CallFailure(kind="api_error", detail="HTTP 500"))) is None


# --- session totals and spend cap -----------------------------------------------------------------


def test_session_totals_sum_only_processed_documents():
    rows = [
        view.row_from_record(record(extracted(truth_payload("A01")), cost="0.04")),
        view.row_from_record(record(failed(), cost="0.03")),
        view.not_processed_row("skipped.pdf", "tope"),
    ]

    totals = view.session_totals(rows)

    assert (totals.documents, totals.processed) == (3, 2)
    assert (totals.extracted, totals.failures) == (1, 1)
    assert totals.cost_usd == Decimal("0.07")
    assert (totals.input_tokens, totals.output_tokens) == (10_000, 4_000)


@pytest.mark.parametrize(
    ("spent", "cap", "allowed"),
    [("0.00", "1.00", True), ("0.99", "1.00", True), ("1.00", "1.00", False), ("1.20", "1.00", False)],
)
def test_cap_check_refuses_at_and_above_the_cap(spent, cap, allowed):
    blocked = view.cap_check(Decimal(spent), Decimal(cap))
    assert (blocked is None) is allowed
    if not allowed:
        assert "tope de gasto" in blocked


def test_a_cap_of_zero_is_refused():
    assert view.cap_check(Decimal(0), Decimal(0)) is not None


# --- formatting -----------------------------------------------------------------------------------


def test_amounts_print_in_the_format_the_documents_use():
    assert view.format_amount(Decimal("338650.00")) == "338.650,00"
    assert view.format_amount(None) == "—"


def test_cost_and_latency_formatting():
    assert view.format_usd(Decimal("0.0376")) == "$0.0376"
    assert view.format_latency(12_300) == "12.3 s"
    assert view.format_latency(None) == "—"


# --- boundaries (PRD 06 R1.1, CC-2) -----------------------------------------------------------------


def test_view_imports_no_framework_and_no_sdk():
    source = Path(view.__file__).read_text(encoding="utf-8")
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not imported & {"streamlit", "anthropic", "httpx2"}
