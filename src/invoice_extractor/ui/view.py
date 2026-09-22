"""What the page shows, as plain data (design D2).

This module is the UI's own logic: turning one extraction record into a row, formatting
values, session totals and the spend-cap decision. It imports no UI framework and no SDK,
so every behaviour here is tested without Streamlit and without an API key.
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from invoice_extractor.client import CallFailure, Parsed
from invoice_extractor.extraction import ExtractionRecord
from invoice_extractor.schema import Extracted, Invoice

# extracted: an invoice came back. model_failure: the model refused to invent one.
# call_failure: the call itself did not produce a usable result. not_processed: no call was made.
OutcomeKind = Literal["extracted", "model_failure", "call_failure", "not_processed"]

INVOICE_TYPE_LABELS = {
    "A": "Factura A",
    "B": "Factura B",
    "C": "Factura C",
    "E": "Factura E",
}
FAILURE_REASON_LABELS = {
    "not_an_invoice": "No es una factura",
    "unsupported_document_type": "Documento fiscal no soportado",
    "illegible": "Ilegible",
    "missing_mandatory_data": "Faltan datos obligatorios",
}
CALL_FAILURE_LABELS = {
    "truncated": "Respuesta cortada (max_tokens)",
    "refused": "El modelo rechazó la solicitud",
    "invalid_output": "Respuesta inválida contra el schema",
    "api_error": "Error de la API",
}


class ResultRow(BaseModel):
    """One document as the table shows it. Every number comes from the call record."""

    model_config = ConfigDict(frozen=True)

    file_name: str
    outcome: OutcomeKind
    invoice_type: str | None = None
    # The machine-readable cause (`not_an_invoice`, `truncated`, ...) when there is one.
    reason: str | None = None
    detail: str | None = None
    issuer: str | None = None
    issue_date: str | None = None
    total: Decimal | None = None
    currency: str | None = None
    attempts: int = 0
    cost_usd: Decimal = Decimal(0)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int | None = None
    model_id: str | None = None
    stop_reason: str | None = None
    request_id: str | None = None

    @property
    def is_success(self) -> bool:
        return self.outcome == "extracted"

    @property
    def label(self) -> str:
        """The one line that says what this document is."""
        if self.outcome == "extracted" and self.invoice_type:
            return INVOICE_TYPE_LABELS.get(self.invoice_type, self.invoice_type)
        if self.outcome == "model_failure":
            return FAILURE_REASON_LABELS.get(self.reason or "", "Falla explícita")
        if self.outcome == "call_failure":
            return CALL_FAILURE_LABELS.get(self.reason or "", "Falla de la llamada")
        return "No procesado"


def row_from_record(record: ExtractionRecord, invoice: Invoice | None = None) -> ResultRow:
    """Build the row for one processed document. `invoice` is derived from the record."""
    call = record.call
    common = {
        "file_name": record.source,
        "attempts": 1,
        "cost_usd": call.cost_usd,
        "input_tokens": call.input_tokens,
        "output_tokens": call.output_tokens,
        "latency_ms": call.latency_ms,
        "model_id": call.model_id,
        "stop_reason": call.stop_reason,
        "request_id": call.request_id,
    }
    if isinstance(call.outcome, CallFailure):
        return ResultRow(outcome="call_failure", reason=call.outcome.kind, detail=call.outcome.detail, **common)

    result = call.outcome.value.result
    if not isinstance(result, Extracted):
        return ResultRow(outcome="model_failure", reason=result.reason, detail=result.detail, **common)

    inv = result.invoice
    return ResultRow(
        outcome="extracted",
        invoice_type=inv.invoice_type,
        issuer=inv.issuer.name,
        issue_date=inv.issue_date.isoformat(),
        total=inv.total,
        currency=inv.currency,
        **common,
    )


def not_processed_row(file_name: str, detail: str) -> ResultRow:
    """A document no call was made for: an unsupported format, or the spend cap."""
    return ResultRow(file_name=file_name, outcome="not_processed", detail=detail)


def invoice_of(record: ExtractionRecord) -> Invoice | None:
    """The extracted invoice of a record, or None when it did not produce one."""
    if not isinstance(record.call.outcome, Parsed):
        return None
    result = record.call.outcome.value.result
    return result.invoice if isinstance(result, Extracted) else None


class SessionTotals(BaseModel):
    model_config = ConfigDict(frozen=True)

    documents: int
    processed: int
    extracted: int
    failures: int
    cost_usd: Decimal
    input_tokens: int
    output_tokens: int


def session_totals(rows: list[ResultRow]) -> SessionTotals:
    processed = [r for r in rows if r.outcome != "not_processed"]
    return SessionTotals(
        documents=len(rows),
        processed=len(processed),
        extracted=sum(1 for r in processed if r.is_success),
        failures=sum(1 for r in processed if not r.is_success),
        cost_usd=sum((r.cost_usd for r in processed), Decimal(0)),
        input_tokens=sum(r.input_tokens for r in processed),
        output_tokens=sum(r.output_tokens for r in processed),
    )


def cap_check(spent_usd: Decimal, cap_usd: Decimal) -> str | None:
    """None when another document may start, otherwise why it may not (CC-5, design D3).

    Checked before each document, so a session can exceed the cap by at most one document.
    """
    if cap_usd <= 0:
        return "el tope de gasto tiene que ser mayor que cero"
    if spent_usd >= cap_usd:
        return f"se alcanzó el tope de gasto de la sesión (${cap_usd:.2f})"
    return None


def format_usd(amount: Decimal) -> str:
    return f"${amount:.4f}"


def format_latency(latency_ms: int | None) -> str:
    return "—" if latency_ms is None else f"{latency_ms / 1000:.1f} s"


def format_amount(amount: Decimal | None) -> str:
    """A printed invoice amount, in the Argentine format the documents use."""
    if amount is None:
        return "—"
    whole, _, fraction = f"{amount:,.2f}".partition(".")
    return f"{whole.replace(',', '.')},{fraction}"
