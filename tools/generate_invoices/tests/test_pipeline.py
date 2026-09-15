import copy

import pytest

from generator.params import generate_params
from generator.pipeline import GenerationError, generate_document
from generator.visibility import build_invoice_ground_truth


def test_success_writes_pdf_and_ground_truth(tmp_path):
    p = generate_params(3001, tipo_cbte=1, n_items=2)
    invoice_gt = build_invoice_ground_truth(p, letter="A")

    result = generate_document(
        doc_id="doc_a",
        params=p,
        invoice_gt=invoice_gt,
        template_name="qr_base.csv",
        out_dir=tmp_path,
    )

    assert result.pdf_path.exists()
    assert result.gt_path.exists()
    assert result.verification.passed


def test_rendering_error_writes_nothing(tmp_path):
    p = generate_params(3002, tipo_cbte=1, n_items=1)
    invoice_gt = build_invoice_ground_truth(p, letter="A")
    manifest_entries = []

    with pytest.raises(GenerationError):
        result = generate_document(
            doc_id="doc_bad_template",
            params=p,
            invoice_gt=invoice_gt,
            template_name="does_not_exist.csv",
            out_dir=tmp_path,
        )
        manifest_entries.append(result)  # never reached

    assert manifest_entries == []
    assert list(tmp_path.iterdir()) == []


def test_verification_failure_writes_nothing(tmp_path):
    p = generate_params(3003, tipo_cbte=1, n_items=1)
    invoice_gt = build_invoice_ground_truth(p, letter="A")
    tampered = copy.deepcopy(invoice_gt)
    tampered["total"] = "999999.99"
    manifest_entries = []

    with pytest.raises(GenerationError):
        result = generate_document(
            doc_id="doc_tampered",
            params=p,
            invoice_gt=tampered,
            template_name="qr_base.csv",
            out_dir=tmp_path,
        )
        manifest_entries.append(result)  # never reached

    assert manifest_entries == []
    assert list(tmp_path.iterdir()) == []
