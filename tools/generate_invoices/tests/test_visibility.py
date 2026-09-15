from decimal import Decimal

from generator.params import generate_params
from generator.visibility import build_extracted_result, build_invoice_ground_truth


def test_factura_a_shows_net_and_vat_breakdown_and_item_rates():
    p = generate_params(1001, tipo_cbte=1, n_items=3)
    gt = build_invoice_ground_truth(p, letter="A")

    assert gt["net_amount"] == str(p.net_amount)
    assert len(gt["vat_breakdown"]) == len(p.vat_breakdown)
    assert gt["vat_breakdown"] == [{"rate": str(r), "amount": str(a)} for r, _b, a in p.vat_breakdown]
    for gt_item, item in zip(gt["items"], p.items):
        assert gt_item["vat_rate"] == str(item.vat_rate)
        assert gt_item["discount"] == "0.00"
    assert gt["vat_amount"] is None
    assert gt["customer"]["name"] == p.customer.name
    assert gt["customer"]["cuit"] == p.customer.cuit


def test_factura_b_to_responsable_inscripto_hides_net_and_item_rates():
    p = generate_params(1002, tipo_cbte=6, customer_vat_condition_label="Responsable Inscripto")
    gt = build_invoice_ground_truth(p, letter="B")

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
    gt = build_invoice_ground_truth(p, letter="B")

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
    gt = build_invoice_ground_truth(p, letter="C")

    assert gt["net_amount"] is None
    assert gt["vat_breakdown"] == []
    for gt_item in gt["items"]:
        assert gt_item["vat_rate"] is None


def test_factura_e_in_usd_shows_currency_and_rate_and_hides_item_vat():
    p = generate_params(1005, tipo_cbte=19, currency="USD", exchange_rate=Decimal("875.0000"))
    gt = build_invoice_ground_truth(p, letter="E")

    assert gt["currency"] == "USD"
    assert gt["exchange_rate"] == "875.0000"
    assert gt["net_amount"] is None
    for gt_item in gt["items"]:
        assert gt_item["vat_rate"] is None


def test_ars_currency_has_null_exchange_rate():
    p = generate_params(1006, tipo_cbte=1)
    gt = build_invoice_ground_truth(p, letter="A")
    assert gt["currency"] == "ARS"
    assert gt["exchange_rate"] is None


def test_items_and_vat_breakdown_are_in_document_order():
    p = generate_params(1007, tipo_cbte=1, n_items=4)
    gt = build_invoice_ground_truth(p, letter="A")
    assert [it["description"] for it in gt["items"]] == [it.description for it in p.items]
    assert [line["rate"] for line in gt["vat_breakdown"]] == [str(r) for r, _b, _a in p.vat_breakdown]


def test_extracted_result_wraps_outcome_and_invoice():
    p = generate_params(1008, tipo_cbte=1)
    result = build_extracted_result(p, letter="A")
    assert result["result"]["outcome"] == "extracted"
    assert "invoice" in result["result"]
