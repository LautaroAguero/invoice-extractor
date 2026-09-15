"""Review subcommand (design D9, tasks.md 6.4): record who/when reviewed a
document, and print its ground truth's null fields as a checklist next to the
PDF (design D2 risk: "a null field that is actually printed goes unnoticed").
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import read_manifest, write_manifest


class ReviewError(Exception):
    pass


def _walk_nulls(obj: Any, path: str, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk_nulls(v, f"{path}.{k}" if path else k, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_nulls(v, f"{path}[{i}]", out)
    elif obj is None:
        out.append(path)


def null_fields_checklist(ground_truth: dict[str, Any]) -> list[str]:
    """Every null leaf path in an `Extracted` ground truth's `invoice`. Empty
    for a `Failed` result: review there is just confirming the printed title."""
    result = ground_truth.get("result", {})
    if result.get("outcome") != "extracted":
        return []
    nulls: list[str] = []
    _walk_nulls(result.get("invoice", {}), "invoice", nulls)
    return nulls


def record_review(
    manifest_path: Path,
    doc_id: str,
    reviewer: str,
    *,
    ground_truth_dir: Path | None = None,
    when: datetime | None = None,
) -> list[str]:
    """Set `reviewed_by`/`reviewed_at` on the manifest entry `doc_id` and return
    its null-field checklist. Raises `ReviewError` if no such entry exists."""
    entries = read_manifest(manifest_path)
    for entry in entries:
        if entry["id"] == doc_id:
            entry["reviewed_by"] = reviewer
            entry["reviewed_at"] = (when or datetime.now(timezone.utc)).isoformat()
            break
    else:
        raise ReviewError(f"no manifest entry with id {doc_id!r}")

    write_manifest(entries, manifest_path)

    checklist: list[str] = []
    if ground_truth_dir is not None:
        gt_path = ground_truth_dir / f"{doc_id}.json"
        if gt_path.exists():
            checklist = null_fields_checklist(json.loads(gt_path.read_text(encoding="utf-8")))
    return checklist


def print_checklist(doc_id: str, checklist: list[str]) -> None:
    print(f"Review checklist for {doc_id}:")
    if not checklist:
        print("  (no null fields to check)")
    for path in checklist:
        print(f"  [ ] {path}")
