"""Generates the 30-document dataset into `ground_truth/` (tasks.md 7.1).

Usage: .venv/Scripts/python -m generator.cli generate [--out-dir ground_truth]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .cases import CASES, Case
from .degrade import degradation_manifest_entry, degrade_pdf, save_image_input_jpeg, save_skewed_scan_pdf
from .manifest import (
    DirtyTreeError,
    build_manifest_entry,
    check_composition,
    ensure_clean_generator_tree,
    write_manifest,
)
from .negatives import NEGATIVE_KINDS, render_negative
from .params import generate_params
from .pipeline import GenerationError, generate_document
from .visibility import build_invoice_ground_truth

TOOL_ROOT = Path(__file__).resolve().parent.parent  # tools/generate_invoices/
REPO_ROOT = TOOL_ROOT.parent.parent  # the extractor repo root: ground_truth/ lives there
DEFAULT_OUT_DIR = REPO_ROOT / "ground_truth"

NEGATIVE_DOCUMENT_KIND = {
    "nota_credito_a": "nota_credito",
    "nota_debito_b": "nota_debito",
    "recibo": "recibo",
    "remito": "remito",
    "presupuesto": "presupuesto",
}


def _case_params(case: Case):
    return generate_params(
        case.seed,
        tipo_cbte=case.tipo_cbte,
        n_items=case.n_items,
        currency=case.currency,
        exchange_rate=case.exchange_rate,
        consumidor_final_unidentified=case.consumidor_final_unidentified,
        customer_vat_condition_label=case.customer_vat_condition_label,
        long_description_item=case.long_description_item,
        concepto=case.concepto,
    )


def generate_invoice_document(case: Case, out_dir: Path) -> dict:
    params = _case_params(case)
    invoice_gt = build_invoice_ground_truth(params, letter=case.letter)

    if case.degradation is None:
        result = generate_document(
            doc_id=case.id, params=params, invoice_gt=invoice_gt,
            template_name=case.template_name, out_dir=out_dir,
        )
        return build_manifest_entry(
            case, file_name=result.pdf_path.name, format_="pdf", source="synthetic",
            pages=_page_count(result.pdf_path),
            expected_outcome="extracted", expected_reason=None,
            gt_check={"checked": result.verification.checked, "skipped": result.verification.skipped, "passed": result.verification.passed},
            degradation=None, printed_letter=case.letter, document_kind="factura",
        )

    # Degraded: render+verify the clean PDF in a scratch dir, then degrade it into
    # the final artifact. The clean PDF itself is not part of the committed dataset.
    with tempfile.TemporaryDirectory() as scratch:
        clean_result = generate_document(
            doc_id=case.id, params=params, invoice_gt=invoice_gt,
            template_name=case.template_name, out_dir=Path(scratch),
        )
        pages_count = _page_count(clean_result.pdf_path)
        degradation_entry = degradation_manifest_entry(clean_result.pdf_path, kind=case.degradation)
        degraded_pages = degrade_pdf(clean_result.pdf_path, seed=case.seed)

        out_dir.mkdir(parents=True, exist_ok=True)
        gt_json_path = out_dir / f"{case.id}.json"
        gt_json_path.write_text(
            json.dumps({"result": {"outcome": "extracted", "invoice": invoice_gt}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if case.degradation == "skewed_scan":
            file_path = out_dir / f"{case.id}.pdf"
            save_skewed_scan_pdf(degraded_pages, file_path, when=datetime(params.issue_date.year, params.issue_date.month, params.issue_date.day, 12, 0, 0))
            format_ = "pdf"
        else:
            file_path = out_dir / f"{case.id}.jpg"
            save_image_input_jpeg(degraded_pages, file_path)
            format_ = "jpg"

    return build_manifest_entry(
        case, file_name=file_path.name, format_=format_, source="synthetic", pages=pages_count,
        expected_outcome="extracted", expected_reason=None,
        gt_check={"checked": clean_result.verification.checked, "skipped": clean_result.verification.skipped, "passed": clean_result.verification.passed},
        degradation=degradation_entry, printed_letter=case.letter, document_kind="factura",
    )


def generate_negative_document(case: Case, out_dir: Path) -> dict:
    params = _case_params(case)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{case.id}.pdf"
    result = render_negative(case.negative_kind, params, out_path=pdf_path)

    gt_path = out_dir / f"{case.id}.json"
    gt_path.write_text(json.dumps(result.ground_truth, ensure_ascii=False, indent=2), encoding="utf-8")

    spec = NEGATIVE_KINDS[case.negative_kind]
    printed_letter = spec["letter"] or None
    return build_manifest_entry(
        case, file_name=pdf_path.name, format_="pdf", source="synthetic",
        pages=_page_count(result.render.pdf_path),
        expected_outcome="explicit_failure", expected_reason=spec["reason"], gt_check=None,
        degradation=None, printed_letter=printed_letter,
        document_kind=NEGATIVE_DOCUMENT_KIND[case.negative_kind],
    )


def _page_count(pdf_path: Path) -> int:
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def generate_dataset(out_dir: Path = DEFAULT_OUT_DIR) -> list[dict]:
    """Generate every case. Raises `GenerationError` on the first failure (spec:
    "Generation fails loudly") — nothing is written for that document, but
    documents already written by earlier cases are left in place."""
    check_composition(CASES)
    entries = []
    for case in CASES:
        if case.negative_kind is None:
            entries.append(generate_invoice_document(case, out_dir))
        else:
            entries.append(generate_negative_document(case, out_dir))
    write_manifest(entries, out_dir / "manifest.jsonl")
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="generator")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate the 30-document dataset")
    gen.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)

    review = sub.add_parser("review", help="Record a human review of one document")
    review.add_argument("doc_id")
    review.add_argument("reviewer")
    review.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)

    args = parser.parse_args(argv)

    if args.command == "generate":
        try:
            ensure_clean_generator_tree()
            entries = generate_dataset(args.out_dir)
        except DirtyTreeError as exc:
            print(f"Generation refused: {exc}", file=sys.stderr)
            return 1
        except GenerationError as exc:
            print(f"Generation failed: {exc}", file=sys.stderr)
            return 1
        print(f"Generated {len(entries)} documents into {args.out_dir}")
        return 0

    if args.command == "review":
        from .review import print_checklist, record_review

        checklist = record_review(args.out_dir / "manifest.jsonl", args.doc_id, args.reviewer, ground_truth_dir=args.out_dir)
        print_checklist(args.doc_id, checklist)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
