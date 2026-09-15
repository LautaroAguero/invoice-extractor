"""Negative rendering (design D5): documents that must be rejected, not extracted.

Rendered by the same engine and templates as an invoice, so they differ from a
real invoice only where the real document differs (hard negatives). Their
ground truth is a `Failed` result and they skip the field-by-field check
entirely: there is no invoice to verify against.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .params import InvoiceParams
from .render import RenderResult, render_invoice
from .visibility import build_failed_result

# tipo_cbte -> (expected_reason, detail, printed title/letter for a human sanity check)
NEGATIVE_KINDS: dict[str, dict] = {
    "nota_credito_a": {"tipo_cbte": 3, "reason": "unsupported_document_type", "letter": "A", "title": "Nota de Crédito"},
    "nota_debito_b": {"tipo_cbte": 7, "reason": "unsupported_document_type", "letter": "B", "title": "Nota de Débito"},
    "recibo": {"tipo_cbte": 4, "reason": "unsupported_document_type", "letter": "A", "title": "Recibo"},
    "remito": {"tipo_cbte": 91, "reason": "not_an_invoice", "letter": "R", "title": "Remito"},
    "presupuesto": {"tipo_cbte": 99, "reason": "not_an_invoice", "letter": "", "title": "Presupuesto"},
}

# Not a real AFIP comprobante: extend the title lookup for tipo_cbte 99 (design D5/2.4).
PRESUPUESTO_TIPOS_FACT = {(99,): "Presupuesto"}


@dataclass
class NegativeResult:
    kind: str
    render: RenderResult
    ground_truth: dict


def render_negative(kind: str, params: InvoiceParams, *, out_path: Path, lineas_max: int = 24) -> NegativeResult:
    """Render one negative document and build its (failed) ground truth.

    `params.tipo_cbte` must already match `NEGATIVE_KINDS[kind]["tipo_cbte"]`;
    the case list (task 6.1) is the source of truth for that pairing.
    """
    spec = NEGATIVE_KINDS[kind]
    if kind == "presupuesto":
        render_result = render_invoice(
            params,
            template_name="presupuesto.csv",
            out_path=out_path,
            lineas_max=lineas_max,
            extra_tipos_fact=PRESUPUESTO_TIPOS_FACT,
            blank_cae=True,
        )
    else:
        render_result = render_invoice(params, template_name="qr_base.csv", out_path=out_path, lineas_max=lineas_max)

    detail = f"{spec['title']} is not a supported invoice."
    ground_truth = build_failed_result(reason=spec["reason"], detail=detail)
    return NegativeResult(kind=kind, render=render_result, ground_truth=ground_truth)
