"""Task 7.2: regenerating the dataset must reproduce it exactly (design D6).

This runs the full generator twice (paying its real cost once per test session
is acceptable here: it is the actual reproducibility contract the spec makes).
"""

import json
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

from generator.cli import DEFAULT_OUT_DIR, generate_dataset
from generator.manifest import read_manifest


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("regenerated")
    generate_dataset(out)
    return out


def test_ground_truth_json_is_byte_identical(regenerated):
    for entry in read_manifest(DEFAULT_OUT_DIR / "manifest.jsonl"):
        committed = (DEFAULT_OUT_DIR / f"{entry['id']}.json").read_bytes()
        regen = (regenerated / f"{entry['id']}.json").read_bytes()
        assert regen == committed, f"{entry['id']}.json differs"


def test_clean_and_negative_documents_are_byte_identical(regenerated):
    for entry in read_manifest(DEFAULT_OUT_DIR / "manifest.jsonl"):
        if entry["degradation"] is not None:
            continue
        committed = (DEFAULT_OUT_DIR / entry["file"]).read_bytes()
        regen = (regenerated / entry["file"]).read_bytes()
        assert regen == committed, f"{entry['file']} differs"


def _rasterize_all_pages(pdf_path: Path) -> list[bytes]:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return [page.render(scale=2.0).to_pil().tobytes() for page in pdf]
    finally:
        pdf.close()


def test_degraded_documents_are_pixel_identical(regenerated):
    degraded = [e for e in read_manifest(DEFAULT_OUT_DIR / "manifest.jsonl") if e["degradation"] is not None]
    assert len(degraded) == 4

    for entry in degraded:
        committed_path = DEFAULT_OUT_DIR / entry["file"]
        regen_path = regenerated / entry["file"]
        if entry["format"] == "jpg":
            with Image.open(committed_path) as a, Image.open(regen_path) as b:
                assert a.tobytes() == b.tobytes(), f"{entry['file']} pixels differ"
        else:
            assert _rasterize_all_pages(committed_path) == _rasterize_all_pages(regen_path), (
                f"{entry['file']} pixels differ"
            )
