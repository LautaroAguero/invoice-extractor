"""Visibility map: parameters -> ground truth (design D3, tasks.md 4.2).

Ground truth is what the rendered letter actually prints, not the generator's
input. Every value here is shaped exactly like the extractor's `ExtractionResult`
(src/invoice_extractor/schema.py) so it can be dropped straight into a
`ground_truth/*.json` file and validated against that schema.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

from .params import (
    VAT_CONDITION_ENUM_BY_LABEL,
    InvoiceParams,
    is_consumidor_final,
    issuer_vat_condition_label,
)


TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


class UnprintableVatRateError(ValueError):
    """A VAT rate has no `IVA<rate>` field in the template, so it cannot be printed."""


@cache
def _vat_line_positions(template_name: str) -> dict[Decimal, tuple[float, float]]:
    """(y, x) of each `IVA<rate>` totals field in a pyfepdf template CSV, keyed by rate.

    pyfepdf prints each VAT line at its template field, not in insertion order, so this
    is the printed order of `vat_breakdown` (design D3).
    """
    positions: dict[Decimal, tuple[float, float]] = {}
    with (TEMPLATES_DIR / template_name).open(encoding="latin-1", newline="") as handle:
        for row in csv.reader(handle, delimiter=";", quotechar="'"):
            name = row[0]
            if name.startswith("IVA") and not name.endswith(".L"):
                try:
                    rate = Decimal(name[3:])
                except ArithmeticError:
                    continue
                positions[rate] = (float(row[3]), float(row[2]))
    return positions


def printed_vat_order(rates: list[Decimal], template_name: str) -> list[Decimal]:
    positions = _vat_line_positions(template_name)
    missing = [rate for rate in rates if rate not in positions]
    if missing:
        raise UnprintableVatRateError(f"{template_name} has no IVA field for rate(s) {missing}")
    return sorted(rates, key=lambda rate: positions[rate])


def _dec(value: Decimal) -> str:
    """Canonical decimal-string form the schema expects: digits, dot, no thousands separator."""
    return str(value)


def document_code(tipo_cbte: int) -> str:
    return "%02d" % tipo_cbte


def build_invoice_ground_truth(params: InvoiceParams, *, letter: str, template_name: str) -> dict[str, Any]:
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

    vat_breakdown: list[dict[str, str]] = []
    if show_vat_breakdown:
        amount_by_rate = {rate: amount for rate, _base, amount in params.vat_breakdown}
        vat_breakdown = [
            {"rate": _dec(rate), "amount": _dec(amount_by_rate[rate])}
            for rate in printed_vat_order(list(amount_by_rate), template_name)
        ]

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
            "vat_condition": VAT_CONDITION_ENUM_BY_LABEL[issuer_vat_condition_label(params.tipo_cbte)],
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


def build_extracted_result(params: InvoiceParams, *, letter: str, template_name: str) -> dict[str, Any]:
    invoice = build_invoice_ground_truth(params, letter=letter, template_name=template_name)
    return {"result": {"outcome": "extracted", "invoice": invoice}}


def build_failed_result(*, reason: str, detail: str) -> dict[str, Any]:
    return {"result": {"outcome": "failed", "reason": reason, "detail": detail}}
