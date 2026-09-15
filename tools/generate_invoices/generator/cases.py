"""The 30-document case list (design D9). The generator reads nothing else.

Seeds are 1001-1030 in id order. Prompt example seeds (PRD 04) use 9000+, disjoint
by construction (spec: "Few-shot examples never come from the evaluation set").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

TIPO_CBTE_BY_LETTER = {"A": 1, "B": 6, "C": 11, "E": 19}


@dataclass(frozen=True)
class Case:
    id: str
    seed: int
    negative_kind: str | None  # None for an in-domain invoice; else a generator.negatives.NEGATIVE_KINDS key
    letter: str | None  # printed letter for an invoice; None resolved later for a negative
    layout: str  # "qr_base" or "qr_variant" (presupuesto counts as qr_base: D4/D5, task 2.4)
    tags: tuple[str, ...] = ()
    n_items: int | None = None
    consumidor_final_unidentified: bool = False
    customer_vat_condition_label: str = "Responsable Inscripto"
    currency: str = "ARS"
    exchange_rate: Decimal | None = None
    concepto: int = 3
    long_description_item: int | None = None
    degradation: str | None = None  # "skewed_scan" | "image_input" | None

    @property
    def tipo_cbte(self) -> int:
        if self.negative_kind is not None:
            from .negatives import NEGATIVE_KINDS

            return NEGATIVE_KINDS[self.negative_kind]["tipo_cbte"]
        return TIPO_CBTE_BY_LETTER[self.letter]

    @property
    def template_name(self) -> str:
        if self.negative_kind == "presupuesto":
            return "presupuesto.csv"
        return "qr_base.csv" if self.layout == "qr_base" else "qr_variant.csv"


def _seeded(cases: list[Case]) -> list[Case]:
    """Assign seeds 1001, 1002, ... in list order (design D9)."""
    out = []
    for i, case in enumerate(cases):
        out.append(_with_seed(case, 1001 + i))
    return out


def _with_seed(case: Case, seed: int) -> Case:
    from dataclasses import replace

    return replace(case, seed=seed)


_RAW_CASES: list[Case] = [
    # --- A: 10 (5 qr_base / 5 qr_variant); multi_page x1, dense_table x1, skewed_scan x1, image_input x1
    Case(id="A01", seed=0, negative_kind=None, letter="A", layout="qr_base"),
    Case(id="A02", seed=0, negative_kind=None, letter="A", layout="qr_base"),
    Case(id="A03", seed=0, negative_kind=None, letter="A", layout="qr_base", tags=("multi_page",), n_items=26, long_description_item=12),
    Case(id="A04", seed=0, negative_kind=None, letter="A", layout="qr_base", tags=("dense_table",), n_items=20),
    Case(id="A05", seed=0, negative_kind=None, letter="A", layout="qr_base", tags=("skewed_scan",), degradation="skewed_scan"),
    Case(id="A06", seed=0, negative_kind=None, letter="A", layout="qr_variant"),
    Case(id="A07", seed=0, negative_kind=None, letter="A", layout="qr_variant"),
    Case(id="A08", seed=0, negative_kind=None, letter="A", layout="qr_variant"),
    Case(id="A09", seed=0, negative_kind=None, letter="A", layout="qr_variant", tags=("image_input",), degradation="image_input"),
    Case(id="A10", seed=0, negative_kind=None, letter="A", layout="qr_variant"),
    # --- B: 7 (4 qr_base / 3 qr_variant); missing_optional x2, multi_page x1, image_input x1
    Case(id="B01", seed=0, negative_kind=None, letter="B", layout="qr_base"),
    Case(id="B02", seed=0, negative_kind=None, letter="B", layout="qr_base"),
    Case(
        id="B03", seed=0, negative_kind=None, letter="B", layout="qr_base", tags=("missing_optional",),
        consumidor_final_unidentified=True, customer_vat_condition_label="Consumidor Final",
    ),
    Case(id="B04", seed=0, negative_kind=None, letter="B", layout="qr_base", tags=("multi_page",), n_items=26),
    Case(id="B05", seed=0, negative_kind=None, letter="B", layout="qr_variant"),
    Case(
        id="B06", seed=0, negative_kind=None, letter="B", layout="qr_variant", tags=("missing_optional",),
        consumidor_final_unidentified=True, customer_vat_condition_label="Consumidor Final",
    ),
    Case(id="B07", seed=0, negative_kind=None, letter="B", layout="qr_variant", tags=("image_input",), degradation="image_input"),
    # --- C: 5 (2 qr_base / 3 qr_variant); missing_optional x1 (no due date), skewed_scan x1
    Case(id="C01", seed=0, negative_kind=None, letter="C", layout="qr_base"),
    Case(id="C02", seed=0, negative_kind=None, letter="C", layout="qr_base", tags=("missing_optional",), concepto=1),
    Case(id="C03", seed=0, negative_kind=None, letter="C", layout="qr_variant"),
    Case(id="C04", seed=0, negative_kind=None, letter="C", layout="qr_variant"),
    Case(id="C05", seed=0, negative_kind=None, letter="C", layout="qr_variant", tags=("skewed_scan",), degradation="skewed_scan"),
    # --- E: 3 (2 qr_base / 1 qr_variant); foreign_currency x3 (USD x2, EUR x1)
    Case(id="E01", seed=0, negative_kind=None, letter="E", layout="qr_base", tags=("foreign_currency",), currency="USD", exchange_rate=Decimal("875.0000"), concepto=2, n_items=2),
    Case(id="E02", seed=0, negative_kind=None, letter="E", layout="qr_base", tags=("foreign_currency",), currency="EUR", exchange_rate=Decimal("950.5000"), concepto=2, n_items=2),
    Case(id="E03", seed=0, negative_kind=None, letter="E", layout="qr_variant", tags=("foreign_currency",), currency="USD", exchange_rate=Decimal("880.2500"), concepto=2, n_items=2),
    # --- Negatives: 5 (2 qr_base / 3 qr_variant); not_an_invoice x2, unsupported_document x3
    Case(id="nota_credito_a", seed=0, negative_kind="nota_credito_a", letter=None, layout="qr_base", tags=("unsupported_document",), n_items=2),
    Case(id="presupuesto", seed=0, negative_kind="presupuesto", letter=None, layout="qr_base", tags=("not_an_invoice",), n_items=2),
    Case(id="nota_debito_b", seed=0, negative_kind="nota_debito_b", letter=None, layout="qr_variant", tags=("unsupported_document",), n_items=2),
    Case(id="recibo", seed=0, negative_kind="recibo", letter=None, layout="qr_variant", tags=("unsupported_document",), n_items=2),
    Case(id="remito", seed=0, negative_kind="remito", letter=None, layout="qr_variant", tags=("not_an_invoice",), n_items=2),
]

CASES: list[Case] = _seeded(_RAW_CASES)
