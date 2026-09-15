"""Visibility map: parameters -> ground truth (design D3, tasks.md 4.2).

Ground truth is what the rendered letter actually prints, not the generator's
input. Every value here is shaped exactly like the extractor's `ExtractionResult`
(src/invoice_extractor/schema.py) so it can be dropped straight into a
`ground_truth/*.json` file and validated against that schema.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .params import (
    ISSUER_VAT_CONDITION_ENUM,
    VAT_CONDITION_ENUM_BY_LABEL,
    InvoiceParams,
    is_consumidor_final,
)


def _dec(value: Decimal) -> str:
    """Canonical decimal-string form the schema expects: digits, dot, no thousands separator."""
    return str(value)


def document_code(tipo_cbte: int) -> str:
    return "%02d" % tipo_cbte


def build_invoice_ground_truth(params: InvoiceParams, *, letter: str) -> dict[str, Any]:
    """The `invoice` object of an `Extracted` result for one in-domain document."""
    show_neto = letter in ("A", "M")
    show_vat_breakdown = letter in ("A", "M")
    customer_shows_vat_rate = letter in ("A", "M") or (
        letter == "B" and is_consumidor_final(params.customer_vat_condition_label)
    )

    items = [
        {
            "code": it.code,
            "description": it.description,
            "quantity": _dec(it.quantity),
            "unit_price": _dec(it.unit_price),
            "discount": _dec(it.discount),
            "vat_rate": _dec(it.vat_rate) if (it.vat_rate and customer_shows_vat_rate) else None,
            "line_amount": _dec(it.line_amount),
        }
        for it in params.items
    ]

    vat_breakdown = (
        [{"rate": _dec(rate), "amount": _dec(amount)} for rate, _base, amount in params.vat_breakdown]
        if show_vat_breakdown
        else []
    )

    if params.customer is None:
        customer = {"name": None, "cuit": None, "address": None}
    else:
        customer = {
            "name": params.customer.name,
            "cuit": params.customer.cuit,
            "address": params.customer.address,
        }
    customer["vat_condition"] = VAT_CONDITION_ENUM_BY_LABEL[params.customer_vat_condition_label]

    return {
        "invoice_type": letter,
        "document_code": document_code(params.tipo_cbte),
        "point_of_sale": "%05d" % params.punto_vta,
        "invoice_number": "%08d" % params.cbte_nro,
        "issue_date": params.issue_date.isoformat(),
        "due_date": params.due_date.isoformat() if params.due_date else None,
        "issuer": {
            "name": params.issuer.name,
            "cuit": params.issuer.cuit,
            "vat_condition": ISSUER_VAT_CONDITION_ENUM,
        },
        "customer": customer,
        "currency": params.currency,
        "exchange_rate": _dec(params.exchange_rate) if params.currency != "ARS" else None,
        "items": items,
        "vat_breakdown": vat_breakdown,
        "other_taxes": [],
        "net_amount": _dec(params.net_amount) if show_neto else None,
        "non_taxed_amount": "0.00",
        "exempt_amount": "0.00",
        "vat_amount": None,
        "total": _dec(params.total),
        "cae": {"number": params.cae, "expiry_date": params.cae_expiry.isoformat()},
    }


def build_extracted_result(params: InvoiceParams, *, letter: str) -> dict[str, Any]:
    return {"result": {"outcome": "extracted", "invoice": build_invoice_ground_truth(params, letter=letter)}}


def build_failed_result(*, reason: str, detail: str) -> dict[str, Any]:
    return {"result": {"outcome": "failed", "reason": reason, "detail": detail}}
