import copy

from generator.params import generate_params
from generator.render import extract_text, render_invoice
from generator.verify import verify_invoice
from generator.visibility import build_invoice_ground_truth


def test_correct_document_passes_and_records_counts(tmp_path):
    p = generate_params(2001, tipo_cbte=1, n_items=3)
    invoice = build_invoice_ground_truth(p, letter="A")

    result = render_invoice(p, template_name="qr_base.csv", out_path=tmp_path / "a.pdf")
    text = extract_text(result.pdf_path)

    outcome = verify_invoice(invoice, text)

    assert outcome.passed
    assert outcome.checked > 0
    assert outcome.skipped == ["currency"]
    assert outcome.failed_field is None


def test_altered_amount_fails_naming_the_field(tmp_path):
    p = generate_params(2002, tipo_cbte=1, n_items=2)
    invoice = build_invoice_ground_truth(p, letter="A")

    result = render_invoice(p, template_name="qr_base.csv", out_path=tmp_path / "a.pdf")
    text = extract_text(result.pdf_path)

    tampered = copy.deepcopy(invoice)
    tampered["total"] = str(float(tampered["total"]) + 1)

    outcome = verify_invoice(tampered, text)

    assert not outcome.passed
    assert outcome.failed_field == "total"


def test_foreign_currency_document_checks_currency_instead_of_skipping(tmp_path):
    from decimal import Decimal

    p = generate_params(2003, tipo_cbte=19, currency="USD", exchange_rate=Decimal("875.0000"), concepto=2)
    invoice = build_invoice_ground_truth(p, letter="E")

    result = render_invoice(p, template_name="qr_base.csv", out_path=tmp_path / "e.pdf")
    text = extract_text(result.pdf_path)

    outcome = verify_invoice(invoice, text)

    assert outcome.passed
    assert outcome.skipped == []
