from generator.cases import CASES, TIPO_CBTE_BY_LETTER
from generator.manifest import check_composition


def test_case_list_passes_the_composition_check():
    check_composition(CASES)  # raises on any mismatch


def test_seeds_are_1001_to_1030_in_order():
    assert [c.seed for c in CASES] == list(range(1001, 1031))


def test_every_invoice_case_resolves_a_tipo_cbte():
    for case in CASES:
        if case.negative_kind is None:
            assert case.tipo_cbte == TIPO_CBTE_BY_LETTER[case.letter]


def test_every_case_resolves_a_template_name():
    for case in CASES:
        assert case.template_name in ("qr_base.csv", "qr_variant.csv", "presupuesto.csv")
        if case.negative_kind == "presupuesto":
            assert case.template_name == "presupuesto.csv"
