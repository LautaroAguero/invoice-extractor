"""Extraction result contract for Argentine invoices (PRD 01 R1, design D1-D8).

Encoding notes (verified in task 2.1, see design D6/D7):
- `anthropic.transform_schema` drops `pattern` and `const` from the grammar and keeps
  only `{"$ref": ...}` for properties that reference `$defs`, losing their description.
  So closed sets are inline `Literal`s, the `outcome` tags are one-value enums, and
  nested models carry their guidance in the class docstring.
- JSON numbers reach `Decimal` through a float, so amounts travel as strings and are
  checked client-side by `DecimalString`.
"""

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, WithJsonSchema

_DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$")
_DECIMAL_FORMAT = (
    'Decimal string: digits with a dot as decimal separator and no thousands separator '
    '(the document prints "338.650,00", return "338650.00").'
)


def _parse_decimal_string(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str) and _DECIMAL_RE.fullmatch(value):
        return Decimal(value)
    raise ValueError(f"expected a decimal string like '338650.00', got {value!r}")


DecimalString = Annotated[
    Decimal,
    BeforeValidator(_parse_decimal_string),
    WithJsonSchema({"type": "string"}),
]


def _decimal_field(label: str, **kwargs: Any) -> Any:
    return Field(description=f"{label} {_DECIMAL_FORMAT}", **kwargs)


InvoiceType = Literal["A", "B", "C", "E"]
Currency = Literal["ARS", "USD", "EUR"]
# ARCA receptor VAT conditions (RG 5616), design D8. No catch-all member on purpose.
VatCondition = Literal[
    "responsable_inscripto",
    "sujeto_exento",
    "consumidor_final",
    "responsable_monotributo",
    "sujeto_no_categorizado",
    "proveedor_del_exterior",
    "cliente_del_exterior",
    "iva_liberado_ley_19640",
    "monotributista_social",
    "iva_no_alcanzado",
    "monotributo_trabajador_independiente_promovido",
]
FailureReason = Literal["not_an_invoice", "unsupported_document_type", "illegible", "missing_mandatory_data"]

INVOICE_TYPES: tuple[str, ...] = get_args(InvoiceType)
CURRENCIES: tuple[str, ...] = get_args(Currency)
VAT_CONDITIONS: tuple[str, ...] = get_args(VatCondition)
FAILURE_REASONS: tuple[str, ...] = get_args(FailureReason)

_VAT_CONDITION_LABELS = (
    'Map the printed label to the value: "IVA Responsable Inscripto" -> responsable_inscripto, '
    '"IVA Sujeto Exento" -> sujeto_exento, "Consumidor Final" -> consumidor_final, '
    '"Responsable Monotributo" -> responsable_monotributo, "Sujeto No Categorizado" -> sujeto_no_categorizado, '
    '"Proveedor del Exterior" -> proveedor_del_exterior, "Cliente del Exterior" -> cliente_del_exterior, '
    '"IVA Liberado - Ley N° 19.640" -> iva_liberado_ley_19640, "Monotributista Social" -> monotributista_social, '
    '"IVA No Alcanzado" -> iva_no_alcanzado, '
    '"Monotributo Trabajador Independiente Promovido" -> monotributo_trabajador_independiente_promovido.'
)
_NULL_IF_NOT_PRINTED = "null when not printed on the document."
_DIGITS = "Digits only, without hyphens or spaces, keeping leading zeros."


def _tag(value: str) -> Any:
    """A one-value enum: the SDK strips `const`, but keeps `enum`."""
    return Annotated[Literal[value], WithJsonSchema({"type": "string", "enum": [value]})]


def _drop_discriminator(schema: dict[str, Any]) -> None:
    # The SDK would paste the mapping into the description as a Python dict repr.
    schema.pop("discriminator", None)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Issuer(_Strict):
    """Emisor: the business issuing the invoice, printed in the header of the document."""

    name: str = Field(description="Razón social of the issuer as printed in the header.")
    cuit: str = Field(
        description=(
            f'"CUIT" of the issuer, printed like "CUIT 30-71234567-1". {_DIGITS} '
            'Not the "IIBB" number, even when it has the same digits.'
        )
    )
    vat_condition: VatCondition = Field(
        description=f'Condición frente al IVA of the issuer, printed in the header. {_VAT_CONDITION_LABELS}'
    )


class Customer(_Strict):
    """Receptor: the customer block ("Sr.(s)", "Dirección", "IVA", "CUIT"). A Factura B to a
    consumidor final may print no name, CUIT or address; those fields are then null."""

    name: str | None = Field(description=f'"Sr.(s)": customer name or razón social. {_NULL_IF_NOT_PRINTED}')
    cuit: str | None = Field(description=f'"CUIT" in the customer block. {_DIGITS} {_NULL_IF_NOT_PRINTED}')
    address: str | None = Field(description=f'"Dirección" exactly as printed on that line. {_NULL_IF_NOT_PRINTED}')
    vat_condition: VatCondition = Field(
        description=f'Condición frente al IVA printed next to "IVA" in the customer block. {_VAT_CONDITION_LABELS}'
    )


class Cae(_Strict):
    """C.A.E. block printed at the bottom of the document ("C.A.E. Nº ... Fecha Vto. CAE: ...")."""

    number: str = Field(description=f'"C.A.E. Nº": the authorization code. {_DIGITS}')
    expiry_date: date = Field(description='"Fecha Vto. CAE" as an ISO date (YYYY-MM-DD).')


class Item(_Strict):
    """One row of the detail table, in document order."""

    code: str | None = Field(description=f'"Articulo" (product code) of the row. null when the row has none.')
    description: str = Field(description='"Descripción" of the row exactly as printed.')
    quantity: DecimalString = _decimal_field('"Cantidad" of the row.')
    unit_price: DecimalString = _decimal_field('"Precio" (unit price) of the row.')
    discount: DecimalString | None = _decimal_field(
        f'"Bonif." amount of the row. null when the table has no "Bonif." column.'
    )
    vat_rate: DecimalString | None = _decimal_field(
        'VAT rate percentage from the "IVA" column ("21%" -> "21", "10,5%" -> "10.5"). The column may show '
        'the row\'s VAT amount glued to the rate ("21%31.500,00"); return only the rate. '
        'null when the table has no "IVA" column (Factura B and C).'
    )
    line_amount: DecimalString = _decimal_field('"Importe" of the row as printed.')


class VatLine(_Strict):
    """One "IVA x%" line of the totals area."""

    rate: DecimalString = _decimal_field('Rate from the line label ("IVA 10,5%" -> "10.5").')
    amount: DecimalString = _decimal_field("Amount printed on that line.")


class OtherTax(_Strict):
    """One other-tax line of the totals area (tributos: percepciones, impuestos internos)."""

    description: str = Field(description="Label of the tax line exactly as printed.")
    amount: DecimalString = _decimal_field("Amount printed on that line.")


class Invoice(_Strict):
    """An Argentine invoice (Factura A, B, C or E). Return only values that are visible on the
    document; optional values that are not printed are null, and are never computed or guessed."""

    invoice_type: InvoiceType = Field(
        description='Invoice letter printed in the box at the top center of the document ("A", "B", "C" or "E").'
    )
    document_code: str | None = Field(
        description=f'Digits of the comprobante code printed under the letter ("COD.01" -> "01"). {_NULL_IF_NOT_PRINTED}'
    )
    point_of_sale: str = Field(
        description=f'Punto de venta: first part of the number printed after "Nº" ("00003-00001542" -> "00003"). {_DIGITS}'
    )
    invoice_number: str = Field(
        description=f'Número de comprobante: second part of that number ("00003-00001542" -> "00001542"). {_DIGITS}'
    )
    issue_date: date = Field(
        description=(
            'Issue date printed as "Fecha", as an ISO date (YYYY-MM-DD). '
            'Not "Fecha Vto. CAE" and not "Fecha de Vencimiento de Pago".'
        )
    )
    due_date: date | None = Field(
        description=f'"Fecha de Vencimiento de Pago" as an ISO date (YYYY-MM-DD). {_NULL_IF_NOT_PRINTED}'
    )
    issuer: Issuer
    customer: Customer
    currency: Currency = Field(
        description='Moneda of the invoice. "ARS" when the document shows no currency (invoices in pesos).'
    )
    exchange_rate: DecimalString | None = _decimal_field(
        f'"Cotización" (tipo de cambio) of a foreign-currency invoice. {_NULL_IF_NOT_PRINTED}'
    )
    items: list[Item] = Field(description="Rows of the detail table, in document order. At least one.", min_length=1)
    vat_breakdown: list[VatLine] = Field(
        description='One entry per "IVA x%" line in the totals area, in document order. Empty when none is printed.'
    )
    other_taxes: list[OtherTax] = Field(
        description="One entry per other-tax line (tributos) in the totals area, in document order. Empty when none is printed."
    )
    net_amount: DecimalString | None = _decimal_field(f'"Neto" (importe neto gravado). {_NULL_IF_NOT_PRINTED}')
    non_taxed_amount: DecimalString | None = _decimal_field(f'"No Gravado". {_NULL_IF_NOT_PRINTED}')
    exempt_amount: DecimalString | None = _decimal_field(f'"Exento". {_NULL_IF_NOT_PRINTED}')
    vat_amount: DecimalString | None = _decimal_field(
        'Total VAT printed as a single amount. null when the document prints only per-rate "IVA x%" lines or no VAT.'
    )
    total: DecimalString = _decimal_field('"Total" (importe total).')
    cae: Cae


class Extracted(_Strict):
    """The document is a supported invoice and every mandatory field is visible."""

    outcome: _tag("extracted") = Field(description='"extracted".')
    invoice: Invoice


class Failed(_Strict):
    """No invoice can be extracted without guessing."""

    outcome: _tag("failed") = Field(description='"failed".')
    reason: FailureReason = Field(
        description=(
            "not_an_invoice: the document is not a fiscal invoice (remito, presupuesto, any other document). "
            "unsupported_document_type: a fiscal document other than Factura A, B, C or E "
            "(Nota de Crédito, Nota de Débito, Factura M, recibo). "
            "illegible: the document cannot be read. "
            "missing_mandatory_data: a supported invoice where a mandatory value is not visible."
        )
    )
    detail: str = Field(
        description="Short explanation. For missing_mandatory_data, name each missing field by its path (for example cae.number)."
    )


class ExtractionResult(_Strict):
    """Result of extracting one document: an invoice, or an explicit failure. Never guess a value."""

    result: Extracted | Failed = Field(
        discriminator="outcome",
        json_schema_extra=_drop_discriminator,
        description='Use "extracted" only when every mandatory value is visible; otherwise "failed" with a reason.',
    )
