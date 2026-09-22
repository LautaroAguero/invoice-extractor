import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

import generator.cli as cli
from generator.cases import CASES
from generator.manifest import build_manifest_entry, read_manifest, write_manifest
from generator.params import generate_params
from generator.review import ReviewError, build_checklist, format_checklist, null_fields_checklist, record_review
from generator.visibility import build_extracted_result

LAUNCHER = Path(__file__).resolve().parent.parent / "run_generator.py"


def _dataset_with_b01(tmp_path) -> Path:
    """A one-document ground truth directory: manifest entry plus a Factura B ground truth."""
    case = next(c for c in CASES if c.id == "B01")
    entry = build_manifest_entry(
        case, file_name="B01.pdf", format_="pdf", source="synthetic", pages=1,
        expected_outcome="extracted", expected_reason=None, gt_check={"passed": True},
        degradation=None, printed_letter=case.letter, document_kind="factura",
    )
    write_manifest([entry], tmp_path / "manifest.jsonl")
    params = generate_params(case.seed, tipo_cbte=6, customer_vat_condition_label="Responsable Inscripto")
    (tmp_path / "B01.json").write_text(json.dumps(build_extracted_result(params, letter="B", template_name="qr_base.csv")), encoding="utf-8")
    return tmp_path


# --- record ------------------------------------------------------------------------------------


def test_record_review_sets_reviewed_by_and_at(tmp_path):
    out = _dataset_with_b01(tmp_path)
    when = datetime(2026, 9, 15, 10, 0, 0, tzinfo=timezone.utc)

    record_review(out / "manifest.jsonl", "B01", "lautaro", when=when)

    (entry,) = read_manifest(out / "manifest.jsonl")
    assert entry["reviewed_by"] == "lautaro"
    assert entry["reviewed_at"] == when.isoformat()


def test_record_review_unknown_id_raises(tmp_path):
    write_manifest([], tmp_path / "manifest.jsonl")
    with pytest.raises(ReviewError):
        record_review(tmp_path / "manifest.jsonl", "does_not_exist", "lautaro")


# --- checklist ---------------------------------------------------------------------------------


def test_checklist_lists_null_fields_and_paths_without_writing(tmp_path):
    out = _dataset_with_b01(tmp_path)
    manifest_before = (out / "manifest.jsonl").read_bytes()

    checklist = build_checklist(out, "B01")

    assert "invoice.net_amount" in checklist.null_fields
    assert "invoice.vat_amount" in checklist.null_fields
    assert "invoice.total" not in checklist.null_fields
    assert checklist.document_path == out / "B01.pdf"
    assert checklist.ground_truth_path == out / "B01.json"
    assert (out / "manifest.jsonl").read_bytes() == manifest_before


def test_checklist_unknown_id_raises(tmp_path):
    out = _dataset_with_b01(tmp_path)
    with pytest.raises(ReviewError):
        build_checklist(out, "does_not_exist")


def test_formatted_checklist_names_fields_and_the_review_command(tmp_path):
    text = format_checklist(build_checklist(_dataset_with_b01(tmp_path), "B01"))
    assert "[ ] invoice.net_amount" in text
    assert "review B01 <reviewer>" in text


def test_null_fields_checklist_is_empty_for_a_failed_result():
    gt = {"result": {"outcome": "failed", "reason": "not_an_invoice", "detail": "x"}}
    assert null_fields_checklist(gt) == []


# --- CLI -----------------------------------------------------------------------------------------


def test_cli_checklist_prints_and_does_not_record(tmp_path, capsys):
    out = _dataset_with_b01(tmp_path)
    assert cli.main(["checklist", "B01", "--out-dir", str(out)]) == 0
    assert "[ ] invoice.net_amount" in capsys.readouterr().out
    assert read_manifest(out / "manifest.jsonl")[0]["reviewed_by"] is None


def test_cli_review_records(tmp_path, capsys):
    out = _dataset_with_b01(tmp_path)
    assert cli.main(["review", "B01", "lautaro", "--out-dir", str(out)]) == 0
    assert read_manifest(out / "manifest.jsonl")[0]["reviewed_by"] == "lautaro"
    assert "Recorded review of B01 by lautaro" in capsys.readouterr().out


def test_cli_unknown_id_is_an_error_not_a_traceback(tmp_path, capsys):
    out = _dataset_with_b01(tmp_path)
    assert cli.main(["checklist", "nope", "--out-dir", str(out)]) == 1
    assert "no manifest entry" in capsys.readouterr().err


def test_launcher_runs_from_another_working_directory(tmp_path):
    out = _dataset_with_b01(tmp_path / "gt")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = subprocess.run(
        [sys.executable, str(LAUNCHER), "checklist", "B01", "--out-dir", str(out)],
        cwd=elsewhere, capture_output=True, text=True, encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr
    assert "[ ] invoice.net_amount" in result.stdout
