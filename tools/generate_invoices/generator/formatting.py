"""Printed-format rules (design D2): the same formatting pyfepdf itself uses.

Used only to verify what should be *found* in the rendered PDF text; it has
nothing to do with the canonical decimal-string form stored in ground truth.
"""

from __future__ import annotations

from decimal import Decimal

from .params import VAT_CONDITION_ENUM_BY_LABEL

VAT_CONDITION_LABEL_BY_ENUM = {v: k for k, v in VAT_CONDITION_ENUM_BY_LABEL.items()}


def format_amount(value: str) -> str:
    """"338650.00" -> "338.650,00": "." thousands separator, "," for decimals."""
    q = Decimal(value).quantize(Decimal("0.01"))
    sign = "-" if q < 0 else ""
    int_part, _, frac_part = f"{abs(q):.2f}".partition(".")
    grouped = f"{int(int_part):,}".replace(",", ".")
    return f"{sign}{grouped},{frac_part}"


def format_vat_rate(value: str) -> str:
    """"21" -> "21%", "10.5" -> "10,5%"."""
    return str(Decimal(value)).replace(".", ",") + "%"


def format_date(iso_date: str) -> str:
    """"2026-08-12" -> "12/08/2026"."""
    y, m, d = iso_date.split("-")
    return f"{d}/{m}/{y}"


def format_cuit(cuit: str) -> str:
    """"30712345671" -> "30-71234567-1"."""
    return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10]}"


def format_document_code(code: str) -> str:
    return f"COD.{code}"


def format_issuer_vat_condition(vat_condition_enum: str) -> str:
    """Printed with the "IVA " prefix in the issuer header block."""
    return f"IVA {VAT_CONDITION_LABEL_BY_ENUM[vat_condition_enum]}"


def format_customer_vat_condition(vat_condition_enum: str) -> str:
    """Printed after the separate "IVA:" label in the customer block, no prefix."""
    return VAT_CONDITION_LABEL_BY_ENUM[vat_condition_enum]


def format_currency(currency: str) -> str:
    """The ISO code is a substring of whatever descriptor pyfepdf prints ("USD: Dólar")."""
    return currency


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())
