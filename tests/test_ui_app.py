"""Smoke test of the page itself (PRD 06 R7.2): it renders fixture results without any model call.

Skipped when the optional UI extra is not installed, so `pytest` still passes without it.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from builders import extracted, failed, make_call, truth_payload
from invoice_extractor.extraction import ExtractionRecord
from invoice_extractor.ui import view

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP = Path(view.__file__).parent / "app.py"


def record(outcome, source: str) -> ExtractionRecord:
    return ExtractionRecord(source=source, prompt_version="v1", call=make_call(outcome, cost="0.0376"))


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")  # never used: no document is processed
    invoice_record = record(extracted(truth_payload("A01")), "A01.pdf")
    negative_record = record(failed("not_an_invoice"), "remito.pdf")

    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state.rows = [
        view.row_from_record(invoice_record),
        view.row_from_record(negative_record),
        view.not_processed_row("tercera.pdf", "se alcanzó el tope de gasto de la sesión ($1.00)"),
    ]
    at.session_state.records = {"A01.pdf": invoice_record, "remito.pdf": negative_record}
    at.session_state.sources = {}
    at.session_state.spent = Decimal("0.0752")
    at.session_state.processed_files = {"A01.pdf", "remito.pdf", "tercera.pdf"}
    return at.run()


def test_the_page_renders_results_without_an_exception(app):
    assert not app.exception


def test_session_metrics_show_the_measured_totals(app):
    metrics = {metric.label: metric.value for metric in app.metric}

    assert metrics["Documentos"] == "2"  # the third was never processed
    assert metrics["Extraídas"] == "1"
    assert metrics["Fallas"] == "1"
    assert metrics["Costo de la sesión"] == "$0.0752"


def test_rows_show_the_classification_and_the_failure(app):
    rendered = " ".join(block.value for block in app.markdown)

    assert "Factura A" in rendered
    assert "No es una factura" in rendered
    assert "No procesado" in rendered


def test_the_detail_shows_the_invoice_fields(app):
    rendered = " ".join(block.value for block in app.markdown)
    invoice = view.invoice_of(app.session_state.records["A01.pdf"])

    assert invoice.issuer.name in rendered
    assert invoice.cae.number in rendered
    assert "Ítems" in rendered and "Totales" in rendered


def test_the_uploader_accepts_the_supported_formats(app):
    (uploader,) = app.get("file_uploader")

    assert set(uploader.proto.type) == {".pdf", ".jpg", ".jpeg", ".png"}
