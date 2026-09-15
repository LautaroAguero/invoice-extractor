## Why

Nothing about the extractor can be measured until there is ground truth, and stage 3 needs it before any prompt or schema is touched. The central risk is ground truth that silently disagrees with what the document prints. Reading pyfepdf showed several ways that happens: the template prints no currency, "Neto" is only printed on type A, and non-last pages print a running subtotal where the total goes. So this change builds a reproducible generator whose ground truth is verified against the rendered PDF, not merely derived from the generator's input.

Stage PRD: [PRD 02 · Dataset](../../../docs/prd/02-dataset.md).

## What Changes

- **Seeded generator** in `tools/generate_invoices/`, built from the spike. It stays isolated: own venv, GPL-3.0, never imported by the extractor. It renders facturas A, B, C and E plus negatives with pyfepdf, and pins the PDF `CreationDate` from the seed so that the same seed gives the same bytes.
- **Two layouts**: the upstream QR template as base (current ARCA format) and one variant with different column labels and a reordered item table. PRD 02 R1.5 said at least 3; exploration reduced it to 2 (see design).
- **Template edits**: currency and exchange-rate fields in both layouts, required by the foreign-currency cases. B invoices keep the current template, with no "IVA Contenido" line.
- **Ground truth from parameters plus a per-type visibility map, verified field by field**: every non-null value, formatted the way it is printed, must appear in the pdfplumber text of the clean PDF. Human review stays as the second layer.
- **Degradation** for 4 documents: rasterize with pypdfium2, rotate, add seeded noise; saved as PDFs with no text layer (2) and as JPG (2). The ground truth of a degraded document is the one verified on its clean source.
- **Dataset of 30 documents** in `ground_truth/`: 25 invoices (A ×10, B ×7, C ×5, E ×3) and 5 negatives (remito, presupuesto, nota de crédito A, nota de débito B, recibo), split 15/15 across layouts, with 17 documents carrying difficulty tags.
- **Expanded manifest** (`ground_truth/manifest.jsonl`): layout, document kind, printed letter, pages, degradation provenance, expected failure reason (recorded and reported, not scored) and the recorded field-check result.
- **Separate real set** (`ground_truth_real/`, git-ignored): two photographed B tickets with CAE and QR, annotated by hand, reported apart from the synthetic metrics and never mixed into them. **Scope change**: PRD 00 and PRD 02 listed real invoices as out of scope.
- Follow-up edits to PRD 00, PRD 02, PRD 03 and PRD 04 so they reflect these decisions.
- **No change to `src/`**. Image ingestion and the text path (path B) belong to the stage 3 change.

## Capabilities

### New Capabilities

- `invoice-dataset`: the evaluation dataset and the generator that produces it. Covers reproducible generation, document composition and difficulty tags, the ground-truth visibility rule and its field-by-field verification, degradation, the manifest, human review, the contamination rule and the separate real set.

### Modified Capabilities

None. The ground truth validates against the existing `invoice-schema` requirements, and none of those requirements change.

## Requirements covered

- PRD 02 R1.1–R1.6 (generator). R1.1 is refined into a tiered reproducibility contract, and R1.5 is reduced to 2 layouts.
- PRD 02 R2 (hard cases). The composition is now fixed, no longer marked "to confirm".
- PRD 02 R3.1–R3.3 (ground truth)
- PRD 02 R4 (manifest), expanded
- PRD 02 R5.1–R5.2 (human review). R5.2 is strengthened from key values to every non-null field.
- PRD 02 R6 (contamination rule)
- Cross-cutting: CC-7 (synthetic data in the repo; the real set is git-ignored)

## Open questions this change depends on

| ID | Question | Status |
|---|---|---|
| OQ-2.1 | Nota de crédito in scope or negative | Resolved 2026-09-14: negative, `unsupported_document_type` |
| OQ-2.2 | Do JPG and no-text-layer cases count toward the 30 | Resolved 2026-09-15: yes, as documents of their own |
| OQ-3.1 | Library for the text path | Resolved 2026-09-15: pdfplumber. Used here only to verify ground truth |
| OQ-3.2 | Scoring of `vat_breakdown` and `other_taxes` | Resolved 2026-09-15: by position (measurement-rules §3) |
| New | B invoices under Ley 27.743 ("IVA Contenido") | Resolved 2026-09-15: not rendered in synthetic B invoices. A dedicated schema field is a PRD 04 candidate |
| New | FCE MiPyMEs (tipo 201) | Resolved 2026-09-15: outside the 30, recorded as a candidate negative |
| New | Expected failure reason scored or reported | Resolved 2026-09-15: recorded and reported, not scored |
| New | Where "IVA Contenido" goes when a real ticket prints it | **Open.** Only affects the hand annotation of the real set; decided when the photos arrive. Does not block the synthetic dataset |

## Impact

- **Generator code and templates:** `tools/generate_invoices/` (new modules, two template CSVs, a presupuesto template), plus `pdfplumber` (brings `pypdfium2`) in its pinned requirements.
- **New data:** `ground_truth/` (30 documents, their ground truth JSON, the manifest), committed. `ground_truth_real/` is git-ignored.
- **Docs:** PRD 00 (data decision), PRD 02 (R1.1, R1.5, R2 composition, R4, R5.2, scope), PRD 03 (report line for failure-reason agreement), PRD 04 (the "IVA Contenido" field as a candidate iteration), and the data paragraph of `openspec/config.yaml`.
- **Extractor:** no changes to `src/` and no model calls, so no token cost for this change.
