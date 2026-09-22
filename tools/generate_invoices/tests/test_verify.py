import copy

from generator.params import generate_params
from generator.render import extract_text, render_invoice
from generator.verify import verify_invoice
from generator.visibility import build_invoice_ground_truth


def test_correct_document_passes_and_records_counts(tmp_path):
    p = generate_params(2001, tipo_cbte=1, n_items=3)
    invoice = build_invoice_ground_truth(p, letter="A", template_name="qr_base.csv")

    result = render_invoice(p, template_name="qr_base.csv", out_path=tmp_path / "a.pdf")
    text = extract_text(result.pdf_path)

    outcome = verify_invoice(invoice, text)

    assert outcome.passed
    assert outcome.checked > 0
    assert outcome.skipped == ["currency"]
    assert outcome.failed_field is None


def test_altered_amount_fails_naming_the_field(tmp_path):
    p = generate_params(2002, tipo_cbte=1, n_items=2)
    invoice = build_invoice_ground_truth(p, letter="A", template_name="qr_base.csv")

    result = render_invoice(p, template_name="qr_base.csv", out_path=tmp_path / "a.pdf")
    text = extract_text(result.pdf_path)

    tampered = copy.deepcopy(invoice)
    tampered["total"] = str(float(tampered["total"]) + 1)

    outcome = verify_invoice(tampered, text)

    assert not outcome.passed
    assert outcome.failed_field == "total"


def test_vat_breakdown_out_of_printed_order_fails(tmp_path):
    # The 148bac7 defect: every line printed, but listed in a different order.
    p = generate_params(1007, tipo_cbte=1, n_items=4)
    invoice = build_invoice_ground_truth(p, letter="A", template_name="qr_base.csv")
    assert len(invoice["vat_breakdown"]) == 2

    result = render_invoice(p, template_name="qr_base.csv", out_path=tmp_path / "a.pdf")
    text = extract_text(result.pdf_path)
    assert verify_invoice(invoice, text).passed

    reversed_lines = copy.deepcopy(invoice)
    reversed_lines["vat_breakdown"].reverse()
    outcome = verify_invoice(reversed_lines, text)

    assert not outcome.passed
    assert outcome.failed_field == "vat_breakdown"


def test_factura_c_prints_the_monotributo_issuer(tmp_path):
    p = generate_params(1004, tipo_cbte=11)
    invoice = build_invoice_ground_truth(p, letter="C", template_name="qr_base.csv")

    result = render_invoice(p, template_name="qr_base.csv", out_path=tmp_path / "c.pdf")
    text = extract_text(result.pdf_path)

    assert "IVA Responsable Monotributo" in text
    assert verify_invoice(invoice, text).passed


def test_factura_b_prints_vat_included_lines(tmp_path):
    p = generate_params(1003, tipo_cbte=6, customer_vat_condition_label="Consumidor Final")
    invoice = build_invoice_ground_truth(p, letter="B", template_name="qr_variant.csv")

    result = render_invoice(p, template_name="qr_variant.csv", out_path=tmp_path / "b.pdf")
    text = extract_text(result.pdf_path)

    assert verify_invoice(invoice, text).passed


def test_foreign_currency_document_checks_currency_instead_of_skipping(tmp_path):
    from decimal import Decimal

    p = generate_params(2003, tipo_cbte=19, currency="USD", exchange_rate=Decimal("875.0000"), concepto=2)
    invoice = build_invoice_ground_truth(p, letter="E", template_name="qr_base.csv")

    result = render_invoice(p, template_name="qr_base.csv", out_path=tmp_path / "e.pdf")
    text = extract_text(result.pdf_path)

    outcome = verify_invoice(invoice, text)

    assert outcome.passed
    assert outcome.skipped == []
