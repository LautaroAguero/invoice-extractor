"""Validates the dataset against the extraction schema (PRD 02 R3, spec:
"Schema validity"). No API calls, no import of the generator
(tools/generate_invoices/ is GPL-3.0 and isolated by design D1) — the mod-11
check below is a small, standalone copy, not a shared import.

Covers both the committed synthetic set (`ground_truth/`, always present) and
the separate real set (`ground_truth_real/`, git-ignored, spec: "Separate real
set"): its tests collect zero cases and are skipped automatically when that
directory does not exist yet (`add-synthetic-dataset` task 8.2).
"""

import json
from pathlib import Path

import pytest

from invoice_extractor.schema import ExtractionResult

REPO_ROOT = Path(__file__).parent.parent
GROUND_TRUTH_DIR = REPO_ROOT / "ground_truth"
GROUND_TRUTH_REAL_DIR = REPO_ROOT / "ground_truth_real"
_CUIT_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def _is_valid_cuit(cuit: str) -> bool:
    if len(cuit) != 11 or not cuit.isdigit():
        return False
    r = sum(int(d) * w for d, w in zip(cuit[:10], _CUIT_WEIGHTS)) % 11
    dv = 0 if r == 0 else 11 - r
    return dv != 10 and dv == int(cuit[10])


def _json_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def _check_schema(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    ExtractionResult.model_validate(payload)


def _check_cuits(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = payload["result"]
    if result["outcome"] != "extracted":
        return
    invoice = result["invoice"]
    assert _is_valid_cuit(invoice["issuer"]["cuit"]), f"{path.name}: issuer CUIT fails mod-11"
    customer_cuit = invoice["customer"]["cuit"]
    if customer_cuit is not None:
        assert _is_valid_cuit(customer_cuit), f"{path.name}: customer CUIT fails mod-11"


@pytest.mark.parametrize("path", _json_files(GROUND_TRUTH_DIR), ids=lambda p: p.stem)
def test_synthetic_ground_truth_validates_against_the_extraction_schema(path):
    _check_schema(path)


@pytest.mark.parametrize("path", _json_files(GROUND_TRUTH_DIR), ids=lambda p: p.stem)
def test_synthetic_in_domain_cuits_pass_mod_11(path):
    _check_cuits(path)


def test_synthetic_dataset_has_thirty_documents():
    assert len(_json_files(GROUND_TRUTH_DIR)) == 30


@pytest.mark.parametrize("path", _json_files(GROUND_TRUTH_REAL_DIR), ids=lambda p: p.stem)
def test_real_ground_truth_validates_against_the_extraction_schema(path):
    _check_schema(path)


@pytest.mark.parametrize("path", _json_files(GROUND_TRUTH_REAL_DIR), ids=lambda p: p.stem)
def test_real_in_domain_cuits_pass_mod_11(path):
    _check_cuits(path)
