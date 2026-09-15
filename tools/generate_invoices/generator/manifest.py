"""Manifest writer and composition check (design D9, tasks.md 6.2/6.3)."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from .cases import Case

REQUIRED_TAGS = (
    "multi_page",
    "foreign_currency",
    "skewed_scan",
    "image_input",
    "missing_optional",
    "not_an_invoice",
    "unsupported_document",
    "dense_table",
)


class CompositionError(ValueError):
    pass


def check_composition(cases: list[Case]) -> None:
    """Spec: "Composition check". Raises `CompositionError` naming what is wrong."""
    if len(cases) != 30:
        raise CompositionError(f"expected 30 documents, got {len(cases)}")

    letter_counts = Counter(c.letter for c in cases if c.negative_kind is None)
    expected_letters = {"A": 10, "B": 7, "C": 5, "E": 3}
    if letter_counts != Counter(expected_letters):
        raise CompositionError(f"invoice letter counts {dict(letter_counts)} != {expected_letters}")

    negative_kinds = [c.negative_kind for c in cases if c.negative_kind is not None]
    if len(negative_kinds) != 5 or len(set(negative_kinds)) != 5:
        raise CompositionError(f"expected 5 distinct negatives, got {negative_kinds}")

    layout_counts = Counter(c.layout for c in cases)
    if layout_counts != Counter({"qr_base": 15, "qr_variant": 15}):
        raise CompositionError(f"layout split {dict(layout_counts)} != 15/15")

    all_tags = {tag for c in cases for tag in c.tags}
    missing_tags = [t for t in REQUIRED_TAGS if t not in all_tags]
    if missing_tags:
        raise CompositionError(f"missing required tags: {missing_tags}")

    tagged = [c for c in cases if c.tags]
    if len(tagged) < 8:
        raise CompositionError(f"expected at least 8 tagged documents, got {len(tagged)}")

    degraded = [c for c in cases if c.degradation is not None]
    if len(degraded) != 4:
        raise CompositionError(f"expected exactly 4 degraded documents, got {len(degraded)}")
    degradation_counts = Counter(c.degradation for c in degraded)
    if degradation_counts != Counter({"skewed_scan": 2, "image_input": 2}):
        raise CompositionError(f"degradation split {dict(degradation_counts)} != 2 skewed_scan / 2 image_input")
    if len({c.id for c in degraded}) != len(degraded):
        raise CompositionError("a degraded document id is duplicated")

    ids = [c.id for c in cases]
    if len(set(ids)) != len(ids):
        raise CompositionError("case ids are not unique")

    seeds = [c.seed for c in cases]
    if len(set(seeds)) != len(seeds):
        raise CompositionError("case seeds are not unique")


TOOL_ROOT = Path(__file__).resolve().parent.parent  # tools/generate_invoices/


class DirtyTreeError(RuntimeError):
    """The generator has uncommitted changes, so the git SHA recorded in the manifest
    would not contain the code that produced the dataset."""


def ensure_clean_generator_tree(run=subprocess.run) -> None:
    """Refuse to generate unless `tools/generate_invoices/` matches HEAD (spec: reproducible generation).

    Untracked files count as changes; ignored files (`.venv/`, `out/`, caches) do not.
    """
    try:
        out = run(
            ["git", "status", "--porcelain", "--", "."], capture_output=True, text=True, check=True, cwd=TOOL_ROOT
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise DirtyTreeError(f"cannot read git status for {TOOL_ROOT}: {exc}") from exc
    if out.stdout.strip():
        raise DirtyTreeError(
            "uncommitted changes in tools/generate_invoices/; commit them before generating, "
            "so the manifest's git_sha reproduces the dataset:\n" + out.stdout.rstrip()
        )


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=Path(__file__).parent
        )
        return out.stdout.strip()
    except Exception:
        return None


def _pyafipws_commit() -> str | None:
    try:
        import pyafipws  # noqa: F401

        return "d595b07"  # pinned commit, requirements.txt
    except Exception:
        return None


def generator_version() -> dict[str, Any]:
    import importlib.metadata

    import fpdf
    import pdfplumber
    import PIL

    return {
        "git_sha": _git_sha(),
        "pyafipws_commit": _pyafipws_commit(),
        "fpdf": getattr(fpdf, "FPDF_VERSION", None),
        "pillow": PIL.__version__,
        "pypdfium2": importlib.metadata.version("pypdfium2"),
        "pdfplumber": pdfplumber.__version__,
    }


def build_manifest_entry(
    case: Case,
    *,
    file_name: str,
    format_: str,
    source: str,
    pages: int,
    expected_outcome: str,
    expected_reason: str | None,
    gt_check: dict[str, Any] | None,
    degradation: dict[str, Any] | None,
    printed_letter: str | None,
    document_kind: str,
    reviewed_by: str | None = None,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    return {
        "id": case.id,
        "file": file_name,
        "format": format_,
        "source": source,
        "seed": case.seed if source == "synthetic" else None,
        "generator_version": generator_version() if source == "synthetic" else None,
        "layout": case.layout,
        "document_kind": document_kind,
        "printed_letter": printed_letter,
        "tags": list(case.tags),
        "pages": pages,
        "degradation": degradation,
        "expected_outcome": expected_outcome,
        "expected_reason": expected_reason,
        "gt_check": gt_check,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
    }


def write_manifest(entries: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False))
            f.write("\n")


def read_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
