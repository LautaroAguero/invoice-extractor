import pytest

from invoice_extractor.evaluation.manifest import REAL_DIR, SYNTHETIC_DIR, load_manifest
from invoice_extractor.schema import Extracted, Failed


def test_synthetic_manifest_has_30_documents_and_tags():
    manifest = load_manifest(SYNTHETIC_DIR)
    by_id = {e.id: e for e in manifest.entries}

    assert len(manifest.entries) == 30
    assert "skewed_scan" in by_id["A05"].tags
    assert by_id["A09"].format == "jpg" and "image_input" in by_id["A09"].tags
    assert all(e.source == "synthetic" for e in manifest.entries)


def test_negatives_expect_a_failure_reason():
    manifest = load_manifest(SYNTHETIC_DIR)
    negatives = [e for e in manifest.entries if e.expected_outcome == "explicit_failure"]

    assert len(negatives) == 5
    assert all(e.expected_reason is not None for e in negatives)
    assert all(e.expected_reason is None for e in manifest.entries if e.expected_outcome == "extracted")


def test_ground_truth_and_document_paths_resolve_for_every_entry():
    manifest = load_manifest(SYNTHETIC_DIR)
    for entry in manifest.entries:
        assert manifest.document_path(entry).is_file()
        result = manifest.load_ground_truth(entry).result
        expected = Extracted if entry.expected_outcome == "extracted" else Failed
        assert isinstance(result, expected), entry.id


def test_generator_version_is_shared_by_the_synthetic_set():
    assert load_manifest(SYNTHETIC_DIR).generator_version["git_sha"]


@pytest.mark.skipif(not REAL_DIR.is_dir(), reason="git-ignored real set is not present")
def test_real_manifest_is_marked_real():
    manifest = load_manifest(REAL_DIR)
    assert len(manifest.entries) == 2
    assert all(e.source == "real" for e in manifest.entries)
    assert manifest.generator_version is None
