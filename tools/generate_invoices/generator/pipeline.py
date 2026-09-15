"""Wires render -> verify -> write so nothing is written on any failure (tasks.md 4.4).

Spec ("Generation fails loudly"): a rendering error or a failed verification
must leave no PDF, image or ground-truth file behind for that document.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .params import InvoiceParams
from .render import extract_text, render_invoice
from .verify import VerificationResult, verify_invoice


class GenerationError(Exception):
    def __init__(self, doc_id: str, reason: str):
        self.doc_id = doc_id
        self.reason = reason
        super().__init__(f"{doc_id}: {reason}")


@dataclass
class GenerationResult:
    doc_id: str
    pdf_path: Path
    gt_path: Path
    verification: VerificationResult


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def generate_document(
    *,
    doc_id: str,
    params: InvoiceParams,
    invoice_gt: dict[str, Any],
    template_name: str,
    out_dir: Path,
    lineas_max: int = 24,
) -> GenerationResult:
    """Render `params`, verify `invoice_gt` against the rendered text, and only then
    write the PDF and ground truth JSON. Raises `GenerationError` (nothing written)
    when rendering raises or verification fails."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{doc_id}.pdf"
    gt_path = out_dir / f"{doc_id}.json"

    try:
        render_result = render_invoice(params, template_name=template_name, out_path=pdf_path, lineas_max=lineas_max)
    except Exception as exc:
        _unlink_if_exists(pdf_path)
        raise GenerationError(doc_id, f"rendering failed: {exc}") from exc

    text = extract_text(render_result.pdf_path)
    verification = verify_invoice(invoice_gt, text)
    if not verification.passed:
        _unlink_if_exists(pdf_path)
        raise GenerationError(doc_id, f"verification failed at {verification.failed_field}")

    result_document = {"result": {"outcome": "extracted", "invoice": invoice_gt}}
    gt_path.write_text(json.dumps(result_document, ensure_ascii=False, indent=2), encoding="utf-8")

    return GenerationResult(doc_id=doc_id, pdf_path=pdf_path, gt_path=gt_path, verification=verification)
