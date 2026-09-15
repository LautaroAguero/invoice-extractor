from generator.cases import CASES
from generator.manifest import build_manifest_entry, read_manifest, write_manifest

REQUIRED_KEYS = {
    "id",
    "file",
    "format",
    "source",
    "seed",
    "generator_version",
    "layout",
    "document_kind",
    "printed_letter",
    "tags",
    "pages",
    "degradation",
    "expected_outcome",
    "expected_reason",
    "gt_check",
    "reviewed_by",
    "reviewed_at",
}


def _case(case_id: str):
    return next(c for c in CASES if c.id == case_id)


def test_invoice_entry_has_every_key():
    case = _case("A01")
    entry = build_manifest_entry(
        case,
        file_name="A01.pdf",
        format_="pdf",
        source="synthetic",
        pages=1,
        expected_outcome="extracted",
        expected_reason=None,
        gt_check={"checked": 20, "skipped": ["currency"], "passed": True},
        degradation=None,
        printed_letter="A",
        document_kind="factura",
    )
    assert set(entry) == REQUIRED_KEYS
    assert entry["degradation"] is None
    assert entry["expected_reason"] is None
    assert entry["reviewed_by"] is None
    assert entry["reviewed_at"] is None
    assert entry["seed"] == case.seed
    assert entry["generator_version"]["pyafipws_commit"] == "d595b07"


def test_degraded_entry_has_every_key_including_degradation():
    case = _case("A05")
    entry = build_manifest_entry(
        case,
        file_name="A05.skewed_scan.pdf",
        format_="pdf",
        source="synthetic",
        pages=1,
        expected_outcome="extracted",
        expected_reason=None,
        gt_check={"checked": 20, "skipped": ["currency"], "passed": True},
        degradation={"source_sha256": "abc", "resolution_dpi": 200, "rotation_degrees_range": [2.0, 5.0], "noise_amplitude": 28, "blur_radius": 0.7},
        printed_letter="A",
        document_kind="factura",
    )
    assert set(entry) == REQUIRED_KEYS
    assert entry["degradation"]["source_sha256"] == "abc"


def test_negative_entry_has_every_key_with_null_seed_and_gt_check():
    case = _case("remito")
    entry = build_manifest_entry(
        case,
        file_name="remito.pdf",
        format_="pdf",
        source="synthetic",
        pages=1,
        expected_outcome="explicit_failure",
        expected_reason="not_an_invoice",
        gt_check=None,
        degradation=None,
        printed_letter="R",
        document_kind="remito",
    )
    assert set(entry) == REQUIRED_KEYS
    assert entry["document_kind"] == "remito"
    assert entry["printed_letter"] == "R"
    assert entry["expected_outcome"] == "explicit_failure"
    assert entry["expected_reason"] == "not_an_invoice"
    assert entry["gt_check"] is None


def test_write_and_read_manifest_roundtrip(tmp_path):
    case = _case("A01")
    entry = build_manifest_entry(
        case, file_name="A01.pdf", format_="pdf", source="synthetic", pages=1,
        expected_outcome="extracted", expected_reason=None, gt_check={"passed": True},
        degradation=None, printed_letter="A", document_kind="factura",
    )
    path = tmp_path / "manifest.jsonl"
    write_manifest([entry], path)
    entries = read_manifest(path)
    assert entries == [entry]
