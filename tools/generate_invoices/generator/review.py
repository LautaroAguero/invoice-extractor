"""Review subcommands (design D9, tasks.md 6.4/6.6).

Review happens in this order:
1. `checklist` shows the document and ground truth paths plus the ground truth's
   null fields, without writing anything. The null fields are the design D2 blind
   spot: a null that is actually printed is not caught by verification.
2. The reviewer compares the document against its ground truth.
3. `review` records who reviewed it and when.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import read_manifest, write_manifest


class ReviewError(Exception):
    pass


@dataclass(frozen=True)
class Checklist:
    doc_id: str
    document_path: Path
    ground_truth_path: Path
    expected_outcome: str
    null_fields: list[str]


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


def _entry(entries: list[dict[str, Any]], doc_id: str) -> dict[str, Any]:
    for entry in entries:
        if entry["id"] == doc_id:
            return entry
    raise ReviewError(f"no manifest entry with id {doc_id!r}")


def build_checklist(ground_truth_dir: Path, doc_id: str) -> Checklist:
    """Read-only: never writes the manifest. Raises `ReviewError` for an unknown id
    or a missing ground truth file."""
    entry = _entry(read_manifest(ground_truth_dir / "manifest.jsonl"), doc_id)
    gt_path = ground_truth_dir / f"{doc_id}.json"
    if not gt_path.exists():
        raise ReviewError(f"ground truth file not found: {gt_path}")
    ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
    return Checklist(
        doc_id=doc_id,
        document_path=ground_truth_dir / entry["file"],
        ground_truth_path=gt_path,
        expected_outcome=entry["expected_outcome"],
        null_fields=null_fields_checklist(ground_truth),
    )


def record_review(manifest_path: Path, doc_id: str, reviewer: str, *, when: datetime | None = None) -> None:
    """Set `reviewed_by`/`reviewed_at` on the manifest entry `doc_id`. Raises
    `ReviewError` if no such entry exists."""
    entries = read_manifest(manifest_path)
    entry = _entry(entries, doc_id)
    entry["reviewed_by"] = reviewer
    entry["reviewed_at"] = (when or datetime.now(timezone.utc)).isoformat()
    write_manifest(entries, manifest_path)


def format_checklist(checklist: Checklist) -> str:
    lines = [
        f"Review checklist for {checklist.doc_id} (expected: {checklist.expected_outcome})",
        f"  document:     {checklist.document_path}",
        f"  ground truth: {checklist.ground_truth_path}",
    ]
    if checklist.expected_outcome == "explicit_failure":
        lines.append("  [ ] the printed title and letter match the expected failure reason in the ground truth")
    if checklist.null_fields:
        lines.append("  Confirm each of these is NOT printed on the document:")
        lines.extend(f"  [ ] {path}" for path in checklist.null_fields)
    elif checklist.expected_outcome == "extracted":
        lines.append("  (no null fields to check)")
    lines.append("  Also compare every non-null value against the document, then record the review:")
    lines.append(f"    run_generator.py review {checklist.doc_id} <reviewer>")
    return "\n".join(lines)
