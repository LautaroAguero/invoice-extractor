import json
from datetime import datetime, timezone

import pytest

from generator.manifest import build_manifest_entry, read_manifest, write_manifest
from generator.cases import CASES
from generator.params import generate_params
from generator.review import ReviewError, null_fields_checklist, record_review
from generator.visibility import build_extracted_result


def _manifest_with_one_entry(tmp_path, case_id="B01"):
    case = next(c for c in CASES if c.id == case_id)
    entry = build_manifest_entry(
        case, file_name=f"{case_id}.pdf", format_="pdf", source="synthetic", pages=1,
        expected_outcome="extracted", expected_reason=None, gt_check={"passed": True},
        degradation=None, printed_letter=case.letter, document_kind="factura",
    )
    manifest_path = tmp_path / "manifest.jsonl"
    write_manifest([entry], manifest_path)
    return manifest_path, case


def test_record_review_sets_reviewed_by_and_at(tmp_path):
    manifest_path, _ = _manifest_with_one_entry(tmp_path)
    when = datetime(2026, 9, 15, 10, 0, 0, tzinfo=timezone.utc)

    record_review(manifest_path, "B01", "lautaro", when=when)

    entries = read_manifest(manifest_path)
    assert entries[0]["reviewed_by"] == "lautaro"
    assert entries[0]["reviewed_at"] == when.isoformat()


def test_record_review_unknown_id_raises():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        manifest_path = Path(d) / "manifest.jsonl"
        write_manifest([], manifest_path)
        with pytest.raises(ReviewError):
            record_review(manifest_path, "does_not_exist", "lautaro")


def test_record_review_returns_null_field_checklist(tmp_path):
    manifest_path, case = _manifest_with_one_entry(tmp_path, case_id="B01")
    p = generate_params(case.seed, tipo_cbte=6, customer_vat_condition_label="Responsable Inscripto")
    gt = build_extracted_result(p, letter="B")
    (tmp_path / "B01.json").write_text(json.dumps(gt), encoding="utf-8")

    checklist = record_review(manifest_path, "B01", "lautaro", ground_truth_dir=tmp_path)

    assert "invoice.net_amount" in checklist
    assert "invoice.vat_amount" in checklist
    assert "invoice.total" not in checklist


def test_null_fields_checklist_is_empty_for_a_failed_result():
    gt = {"result": {"outcome": "failed", "reason": "not_an_invoice", "detail": "x"}}
    assert null_fields_checklist(gt) == []
