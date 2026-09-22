"""Seeded parameter generation: parties, items, rates, dates, amounts (tasks.md 4.1).

`InvoiceParams` holds the full business truth of one invoice (everything needed to
render it and to compute exact totals), independent of what a given letter prints.
`generator/visibility.py` maps this to what the letter actually shows.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from .identifiers import generate_cae, generate_cuit

CENT = Decimal("0.01")

ITEM_DESCRIPTIONS = [
    ("SRV-01", "Soporte tecnico mensual"),
    ("HW-220", "Router dual band AX3000"),
    ("LIB-07", "Manual de configuracion impreso"),
    ("SRV-02", "Consultoria de infraestructura"),
    ("HW-045", "Switch administrable 24 puertos"),
    ("SRV-03", "Mantenimiento preventivo de servidores"),
    ("HW-118", "Cable de red categoria 6 (rollo 300m)"),
    ("SRV-04", "Licencia anual de monitoreo"),
    ("HW-092", "Disco SSD 1TB"),
    ("SRV-05", "Migracion de base de datos"),
]

CUSTOMER_NAMES = [
    ("Distribuidora Los Andes S.R.L.", "Av. San Martin 1234, Mendoza"),
    ("Comercial del Sur S.A.", "Ruta 3 Km 12, Bahia Blanca"),
    ("Tecnologia Patagonica S.R.L.", "Belgrano 890, Neuquen"),
    ("Insumos del Litoral S.A.", "Bv. Pellegrini 456, Santa Fe"),
    ("Grupo Cuyo Comercial S.R.L.", "San Juan 234, San Rafael"),
]

VAT_RATES = (Decimal("21"), Decimal("10.5"))

# How a letter prices its items (design D1/D2 of fix-synthetic-fiscal-consistency):
# "net"   (A): printed prices exclude VAT; VAT is added and discriminated.
# "gross" (B): printed prices include VAT; lines sum to the total, VAT is not printed.
# "none"  (C, E): no VAT at all; lines sum to the total.
Pricing = Literal["net", "gross", "none"]
PRICING_BY_TIPO_CBTE: dict[int, Pricing] = {6: "gross", 7: "gross", 11: "none", 19: "none"}


def pricing_for(tipo_cbte: int) -> Pricing:
    """Letters not listed (A and the non-invoice negatives) keep net pricing."""
    return PRICING_BY_TIPO_CBTE.get(tipo_cbte, "net")

ISSUER_NAME = "Tecnored Patagonia S.A."
ISSUER_ADDRESS = "Belgrano 455, Neuquen"
ISSUER_PHONE = "Tel. 0299 444-1234"
# A Factura C is issued by a monotributista; every other letter here by a Responsable Inscripto.
_ISSUER_VAT_CONDITION_LABEL_BY_TIPO_CBTE = {11: "Responsable Monotributo"}

# Printed customer VAT-condition labels this generator uses, mapped to the
# extractor's VatCondition enum (src/invoice_extractor/schema.py). Extend only
# if a case actually needs another label.
VAT_CONDITION_ENUM_BY_LABEL = {
    "Responsable Inscripto": "responsable_inscripto",
    "Consumidor Final": "consumidor_final",
    "Responsable Monotributo": "responsable_monotributo",
    "IVA Sujeto Exento": "sujeto_exento",
}


def issuer_vat_condition_label(tipo_cbte: int) -> str:
    """The issuer's printed VAT condition, shared by the renderer and the ground truth."""
    return _ISSUER_VAT_CONDITION_LABEL_BY_TIPO_CBTE.get(tipo_cbte, "Responsable Inscripto")


def is_consumidor_final(vat_condition_label: str) -> bool:
    """Mirrors pyfepdf's own check (pyfepdf.py ~:1183-1184) for whether a B invoice
    shows the per-item VAT rate."""
    upper = vat_condition_label.upper()
    return ("CONS" in upper and "FINAL" in upper) or ("EXENTO" in upper)


@dataclass
class Item:
    code: str | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    vat_rate: Decimal | None
    discount: Decimal = Decimal("0.00")
    # True on a Factura B: `unit_price` and `line_amount` are the printed, VAT-included values.
    vat_included: bool = False

    @property
    def line_amount(self) -> Decimal:
        """The printed "Importe" of the row: net on A, VAT-included on B, VAT-free on C/E."""
        return (self.quantity * self.unit_price - self.discount).quantize(CENT)

    @property
    def net_amount(self) -> Decimal:
        if self.vat_included and self.vat_rate:
            return (self.line_amount / (1 + self.vat_rate / Decimal(100))).quantize(CENT, ROUND_HALF_UP)
        return self.line_amount

    @property
    def vat_amount(self) -> Decimal:
        if not self.vat_rate:
            return Decimal("0.00")
        if self.vat_included:
            # The remainder, so net + VAT equals the printed line exactly.
            return self.line_amount - self.net_amount
        return (self.line_amount * self.vat_rate / Decimal(100)).quantize(CENT)

    @property
    def gross_amount(self) -> Decimal:
        return self.net_amount + self.vat_amount


@dataclass
class Party:
    name: str
    cuit: str
    address: str


@dataclass
class InvoiceParams:
    seed: int
    tipo_cbte: int
    punto_vta: int
    cbte_nro: int
    issue_date: date
    due_date: date | None
    concepto: int
    issuer: Party
    customer: Party | None  # None: unidentified consumidor final (no name/cuit/address printed)
    customer_vat_condition_label: str
    items: list[Item]
    currency: str
    exchange_rate: Decimal | None
    cae: str
    cae_expiry: date

    @property
    def net_amount(self) -> Decimal:
        return sum((it.net_amount for it in self.items), Decimal("0.00"))

    @property
    def vat_amount(self) -> Decimal:
        return sum((it.vat_amount for it in self.items), Decimal("0.00"))

    @property
    def total(self) -> Decimal:
        return (self.net_amount + self.vat_amount).quantize(CENT)

    @property
    def vat_breakdown(self) -> list[tuple[Decimal, Decimal, Decimal]]:
        """[(rate, base, amount), ...] in first-seen-rate order."""
        order: list[Decimal] = []
        totals: dict[Decimal, tuple[Decimal, Decimal]] = {}
        for it in self.items:
            if not it.vat_rate:
                continue
            if it.vat_rate not in totals:
                order.append(it.vat_rate)
                totals[it.vat_rate] = (Decimal("0.00"), Decimal("0.00"))
            base, amt = totals[it.vat_rate]
            totals[it.vat_rate] = (base + it.net_amount, amt + it.vat_amount)
        return [(rate, *totals[rate]) for rate in order]


def generate_params(
    seed: int,
    *,
    tipo_cbte: int,
    n_items: int | None = None,
    currency: str = "ARS",
    exchange_rate: Decimal | None = None,
    consumidor_final_unidentified: bool = False,
    customer_vat_condition_label: str = "Responsable Inscripto",
    long_description_item: int | None = None,
    punto_vta: int = 5,
    cbte_nro: int | None = None,
    concepto: int = 3,
    issue_date: date | None = None,
) -> InvoiceParams:
    """Deterministic invoice parameters for one case: same seed -> equal parameters."""
    rng = random.Random(seed)
    pricing = pricing_for(tipo_cbte)

    issue_date = issue_date or (date(2026, 1, 5) + timedelta(days=rng.randint(0, 250)))
    due_date = None if concepto == 1 else issue_date + timedelta(days=30)

    issuer = Party(name=ISSUER_NAME, cuit=generate_cuit(rng, prefix="30"), address=ISSUER_ADDRESS)

    customer: Party | None
    if consumidor_final_unidentified:
        customer = None
    else:
        name, address = rng.choice(CUSTOMER_NAMES)
        customer = Party(name=name, cuit=generate_cuit(rng), address=address)

    n_items = n_items if n_items is not None else rng.randint(2, 4)
    pool = ITEM_DESCRIPTIONS[:]
    rng.shuffle(pool)
    items: list[Item] = []
    for i in range(n_items):
        code, desc = pool[i % len(pool)]
        # Quantized to match the template's printed format (FmtCantidad/FmtPrecio "0.2"):
        # every amount-like value prints with exactly 2 decimals, e.g. "1,00" not "1".
        qty = Decimal(rng.randint(1, 5)).quantize(CENT)
        unit_price = Decimal(rng.randint(500, 1500) * 100).quantize(CENT)
        # Always drawn, so every letter consumes the same random sequence (design D1/D2).
        rate = rng.choice(VAT_RATES) if currency == "ARS" else Decimal("0")
        if pricing == "none":
            rate = None
        if long_description_item == i:
            desc = (
                f"{desc} - descripcion extendida para verificar el ajuste de texto en la "
                "columna de descripcion cuando el contenido supera ampliamente el ancho "
                "disponible de la celda en el detalle del comprobante"
            )
        items.append(
            Item(
                code=code, description=desc, quantity=qty, unit_price=unit_price, vat_rate=rate,
                vat_included=pricing == "gross",
            )
        )

    resolved_cbte_nro = cbte_nro if cbte_nro is not None else rng.randint(1, 9999)

    return InvoiceParams(
        seed=seed,
        tipo_cbte=tipo_cbte,
        punto_vta=punto_vta,
        cbte_nro=resolved_cbte_nro,
        issue_date=issue_date,
        due_date=due_date,
        concepto=concepto,
        issuer=issuer,
        customer=customer,
        customer_vat_condition_label=customer_vat_condition_label,
        items=items,
        currency=currency,
        exchange_rate=exchange_rate,
        cae=generate_cae(rng),
        cae_expiry=issue_date + timedelta(days=10),
    )
