import json
from decimal import Decimal

import pytest

from generator.cases import CASES
from generator.cli import DEFAULT_OUT_DIR, _case_params
from generator.params import generate_params
from generator.visibility import (
    UnprintableVatRateError,
    build_extracted_result,
    build_invoice_ground_truth,
    printed_vat_order,
)


def test_factura_a_shows_net_and_vat_breakdown_and_item_rates():
    p = generate_params(1001, tipo_cbte=1, n_items=3)
    gt = build_invoice_ground_truth(p, letter="A", template_name="qr_base.csv")

    assert gt["net_amount"] == str(p.net_amount)
    assert len(gt["vat_breakdown"]) == len(p.vat_breakdown)
    amounts = {str(r): str(a) for r, _b, a in p.vat_breakdown}
    assert {line["rate"]: line["amount"] for line in gt["vat_breakdown"]} == amounts
    for gt_item, item in zip(gt["items"], p.items):
        assert gt_item["vat_rate"] == str(item.vat_rate)
        assert gt_item["discount"] == "0.00"
    assert gt["vat_amount"] is None
    assert gt["customer"]["name"] == p.customer.name
    assert gt["customer"]["cuit"] == p.customer.cuit


def test_factura_b_to_responsable_inscripto_hides_net_and_item_rates():
    p = generate_params(1002, tipo_cbte=6, customer_vat_condition_label="Responsable Inscripto")
    gt = build_invoice_ground_truth(p, letter="B", template_name="qr_base.csv")

    assert gt["net_amount"] is None
    assert gt["vat_breakdown"] == []
    assert gt["vat_amount"] is None
    for gt_item in gt["items"]:
        assert gt_item["vat_rate"] is None
    assert gt["customer"]["vat_condition"] == "responsable_inscripto"


def test_factura_b_to_consumidor_final_unidentified_shows_item_rate_but_no_identity():
    p = generate_params(
        1003,
        tipo_cbte=6,
        consumidor_final_unidentified=True,
        customer_vat_condition_label="Consumidor Final",
    )
    gt = build_invoice_ground_truth(p, letter="B", template_name="qr_base.csv")

    assert gt["customer"]["name"] is None
    assert gt["customer"]["cuit"] is None
    assert gt["customer"]["address"] is None
    assert gt["customer"]["vat_condition"] == "consumidor_final"
    assert gt["net_amount"] is None
    assert gt["vat_breakdown"] == []
    for gt_item, item in zip(gt["items"], p.items):
        assert gt_item["vat_rate"] == str(item.vat_rate)


def test_factura_c_hides_item_vat_rate_and_net():
    p = generate_params(1004, tipo_cbte=11)
    gt = build_invoice_ground_truth(p, letter="C", template_name="qr_base.csv")

    assert gt["net_amount"] is None
    assert gt["vat_breakdown"] == []
    for gt_item in gt["items"]:
        assert gt_item["vat_rate"] is None


def test_factura_c_is_issued_by_a_monotributista_without_vat():
    p = generate_params(1004, tipo_cbte=11)
    gt = build_invoice_ground_truth(p, letter="C", template_name="qr_base.csv")

    assert gt["issuer"]["vat_condition"] == "responsable_monotributo"
    assert sum(Decimal(it["line_amount"]) for it in gt["items"]) == Decimal(gt["total"])


def test_factura_b_to_consumidor_final_prints_vat_included_lines_with_rates():
    p = generate_params(
        1003, tipo_cbte=6, consumidor_final_unidentified=True, customer_vat_condition_label="Consumidor Final"
    )
    gt = build_invoice_ground_truth(p, letter="B", template_name="qr_base.csv")

    assert all(gt_item["vat_rate"] is not None for gt_item in gt["items"])
    assert gt["issuer"]["vat_condition"] == "responsable_inscripto"
    # VAT-included lines: they add up to the total, and each exceeds its net.
    assert sum(Decimal(it["line_amount"]) for it in gt["items"]) == Decimal(gt["total"])
    assert all(item.line_amount > item.net_amount for item in p.items)


def test_factura_e_in_usd_shows_currency_and_rate_and_hides_item_vat():
    p = generate_params(1005, tipo_cbte=19, currency="USD", exchange_rate=Decimal("875.0000"))
    gt = build_invoice_ground_truth(p, letter="E", template_name="qr_base.csv")

    assert gt["currency"] == "USD"
    assert gt["exchange_rate"] == "875.0000"
    assert gt["net_amount"] is None
    for gt_item in gt["items"]:
        assert gt_item["vat_rate"] is None


def test_ars_currency_has_null_exchange_rate():
    p = generate_params(1006, tipo_cbte=1)
    gt = build_invoice_ground_truth(p, letter="A", template_name="qr_base.csv")
    assert gt["currency"] == "ARS"
    assert gt["exchange_rate"] is None


def test_items_and_vat_breakdown_are_in_document_order():
    p = generate_params(1007, tipo_cbte=1, n_items=4)
    gt = build_invoice_ground_truth(p, letter="A", template_name="qr_base.csv")
    assert [it["description"] for it in gt["items"]] == [it.description for it in p.items]
    # The template prints 10.5% above 21%, whatever order the items first used them.
    assert [line["rate"] for line in gt["vat_breakdown"]] == ["10.5", "21"]


@pytest.mark.parametrize("doc_id", ["A03", "A04", "A07", "A10"])
def test_vat_breakdown_matches_the_hand_corrected_ground_truth(doc_id):
    # 148bac7 fixed these four to the printed order by hand; the generator now agrees.
    case = next(c for c in CASES if c.id == doc_id)
    gt = build_invoice_ground_truth(_case_params(case), letter=case.letter, template_name=case.template_name)
    committed = json.loads((DEFAULT_OUT_DIR / f"{doc_id}.json").read_text(encoding="utf-8"))
    assert gt["vat_breakdown"] == committed["result"]["invoice"]["vat_breakdown"]


def test_rate_without_a_template_field_fails():
    with pytest.raises(UnprintableVatRateError):
        printed_vat_order([Decimal("21"), Decimal("19")], "qr_base.csv")


@pytest.mark.parametrize("case", [c for c in CASES if c.letter in ("A", "E")], ids=lambda c: c.id)
def test_a_and_e_ground_truth_is_unchanged(case):
    # The B/C pricing change keeps every random draw, so A and E come out as committed.
    gt = build_extracted_result(_case_params(case), letter=case.letter, template_name=case.template_name)
    committed = json.loads((DEFAULT_OUT_DIR / f"{case.id}.json").read_text(encoding="utf-8"))
    assert gt == committed


def test_extracted_result_wraps_outcome_and_invoice():
    p = generate_params(1008, tipo_cbte=1)
    result = build_extracted_result(p, letter="A", template_name="qr_base.csv")
    assert result["result"]["outcome"] == "extracted"
    assert "invoice" in result["result"]
