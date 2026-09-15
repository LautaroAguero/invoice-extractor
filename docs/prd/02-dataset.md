# PRD 02 · Dataset

Status: draft · Stage 2 of 5 · Depends on: PRD 01 (schema), [measurement rules](../measurement-rules.md) · Course estimate: ~3 h

## Why

Without a labelled dataset, nobody can say how good the extractor is, and every later change is a guess. This stage produces the ground truth before anything is optimized. If we optimize before we can measure, we will "fix" things that were not broken.

## Scope

**In**
- A seeded, reproducible synthetic invoice generator in `tools/generate_invoices/`, built from the spike.
- Exactly 30 documents with ground truth in `ground_truth/`, ≥8 of them hard cases.
- A dataset manifest describing each document.
- A human review pass over every document.
- A separate, git-ignored, hand-annotated real set (`ground_truth_real/`, 2 documents), reported apart from the synthetic metrics.

**Out**
- Real invoices as part of the measured (headline) dataset. The separate real set exists to sanity-check the synthetic templates, not to be scored alongside them.
- The evaluation harness (PRD 03).
- Prompt or schema changes driven by what the dataset reveals (PRD 04).

## Requirements

### R1 · Generator

- **R1.1 Reproducible, in tiers.** Documents are generated from a seed and a parameter set. Given the same seed and the same pinned generator dependencies: ground truth and the clean PDF (including its creation date, pinned rather than left to `datetime.now()`) are byte-identical; a degraded document is pixel-identical, under the recorded Pillow/pypdfium2 versions (JPEG bytes can differ across libjpeg builds, so that tier's contract is pixels, not bytes). The generator version — git SHA, the pinned pyafipws commit and every pinned rendering dependency version — is recorded for every synthetic document.
- **R1.2 Fails loudly.** It runs with `LanzarExcepciones = True`. A rendering error, or a ground truth value that fails the field-by-field check (R5.2), aborts that document; nothing is written for it.
- **R1.3 Valid synthetic identifiers.** Every CUIT carries a correct mod-11 check digit and a legal-entity prefix (30, 33 or 34), never a prefix assigned to natural persons. CAE numbers have 14 digits.
- **R1.4 Arithmetic consistent by construction.** Items sum to net, VAT per rate matches its base, and net plus non-taxed plus exempt plus VAT plus other taxes equals the total. Values are exact decimals with explicit rounding.
- **R1.5 Two visual layouts.** `qr_base` (the upstream QR template, current ARCA format) and `qr_variant` (different item-table labels, unit price and line amount columns swapped). Reduced from an original target of 3: exploration found little added diagnostic value at n=30 for a third layout, and it stays a candidate PRD 04 lever if stage 3 shows layout-dependent errors (design D4). Covers invoice types A, B, C and E, 1–30 items per document, mixed VAT rates (21% and 10.5%), and optional fields present or absent.
- **R1.6 Isolated.** It has its own venv and requirements, is GPL-3.0 and is never imported by the extractor package.

### R2 · Composition (fixed)

Exactly 30 documents: **25 in-domain invoices** (A ×10, B ×7, C ×5, E ×3) and **5 negatives** (1 remito, 1 presupuesto, 1 nota de crédito A, 1 nota de débito B, 1 recibo), split 15/15 between the two layouts. 17 documents carry a difficulty tag (at least 8 required); every tag below appears at least once.

| Tag | What | How it is produced |
|---|---|---|
| `multi_page` | ≥2 pages | 26 items, over `lineas_max` (24) |
| `dense_table` | Many items on one page | 20 items, under the page-break threshold |
| `foreign_currency` | Factura E in USD or EUR with exchange rate | `moneda_id` `DOL`/`060` + a printed rate; 3 of 3 E's (USD ×2, EUR ×1) |
| `skewed_scan` | Rotated, noisy raster, no text layer | Rasterize (pypdfium2, 200dpi), rotate ±[2°,5°], add noise + light blur, save as Pillow PDF |
| `image_input` | JPG instead of PDF | Same degradation, saved as single-page JPEG (quality 70) |
| `missing_optional` | Customer identity or due date absent | B to a consumidor final without identification (`tipo_doc` 99); C with `concepto=1` (no due date) |
| `not_an_invoice` | A document that is not a fiscal invoice; expected reason `not_an_invoice` | Remito (`tipo_cbte` 91, letter R); Presupuesto (a third template derived from `qr_base`: no CAE/QR, "Documento no válido como factura") |
| `unsupported_document` | A fiscal document other than A/B/C/E that looks exactly like an invoice; expected reason `unsupported_document_type` | Nota de crédito A (`tipo_cbte` 3), Nota de débito B (`tipo_cbte` 7), Recibo (`tipo_cbte` 4, letter A) |

Each of the 4 degraded documents (2 `skewed_scan`, 2 `image_input`) is a distinct invoice; `multi_page` and `image_input` never share a case because a JPG case is always single-page.

### R3 · Ground truth

- **R3.1 Visible truth rule.** Ground truth is **what is visible on the rendered document**, not the dict fed to the generator. If the template truncates or wraps a description or reformats a number, the ground truth follows the document. Optional values that are not printed are `null` and are never computed (for example `net_amount` on a Factura B). Synthetic B invoices never print an "IVA Contenido" line (Ley 27.743): the template has no field for it (see Open questions).
  - **Exception, `currency`:** when the document prints no currency, ground truth is `ARS`. This is the fiscal convention stated in the schema field description, not an inference (stage 1 design D1).
- **R3.2 Schema-shaped.** Ground truth for `expected_outcome = extracted` validates against the PRD 01 result schema. Ground truth for a negative records the expected failure (`not_an_invoice` or `unsupported_document_type`), not an invoice.
- **R3.3 Format follows the measurement rules.** Absent optional fields are explicit `null` (never omitted keys), because `null`=`null` scores as correct. Items keep document order, because items are matched by position. Amounts are exact decimal strings, because amounts are compared exactly.

### R4 · Manifest

`ground_truth/manifest.jsonl`, one line per document with: `id`, `file`, `format` (pdf/jpg), `source` (`synthetic`/`real`), `seed`, `generator_version`, `layout`, `document_kind`, `printed_letter`, `tags`, `pages`, `degradation` (source hash + parameters, for a degraded document), `expected_outcome` (`extracted`/`explicit_failure`), `expected_reason`, `gt_check` (fields checked/skipped and pass/fail, R5.2), `reviewed_by`, `reviewed_at`. Fields that do not apply are `null`. `printed_letter` records the letter printed on the document without implying its invoice type: a nota de crédito A has `printed_letter` `A` and `expected_outcome` `explicit_failure`.

### R5 · Human review

- **R5.1** Every document is opened and compared by eye against its ground truth, using a checklist of that document's `null` fields (a generator subcommand prints it) so a value that should be `null` but is actually printed does not go unnoticed. With 30 documents this takes minutes, and it is the only defense against R3.1 violations that automated verification cannot catch (a common string like "0,00" matching in the wrong cell, or a `null` that is actually printed).
- **R5.2** Before ground truth is written, every non-null leaf value is formatted the way the document prints it and checked against the clean PDF's text (pdfplumber, whitespace collapsed). A document with any value not found fails generation (R1.2); the number of fields checked and skipped, and the pass/fail result, are recorded in the manifest (`gt_check`). This runs automatically as part of generation — it is not a separate, optional pass — and R5.1 remains the second layer for what it structurally cannot catch.

### R6 · Contamination rule

Documents used as few-shot examples in prompts (PRD 04) are generated with seeds disjoint from the evaluation set and never taken from `ground_truth/`.

## Acceptance criteria

- [x] `ground_truth/` holds exactly 30 documents, each with a ground truth JSON and a manifest entry.
- [x] 17 documents carry hard-case tags covering every row of the R2 table (≥8 required).
- [x] 2 documents are JPG and 2 PDFs have no text layer.
- [x] Regenerating from the manifest seeds reproduces byte-identical ground truth and clean documents, and pixel-identical degraded documents.
- [ ] Every manifest entry has `reviewed_by`/`reviewed_at` filled in (pending human review, R5.1).
- [x] Every `extracted` ground truth validates against the result schema, and every in-domain CUIT passes the check digit (`tests/test_dataset.py`).
- [x] No real person or company data appears anywhere in the synthetic dataset; the real set's personal data is covered and the set itself is git-ignored.

## Risks

| Risk | Mitigation |
|---|---|
| Synthetic data is too clean, so baseline precision is near 100% and there is nothing to iterate on | Hard cases, degradation and dense tables are mandatory, not optional; README declares the synthetic limitation |
| Ground truth drifts from what is rendered (truncation, formatting) | R3.1 + R5 |
| pyfepdf breaks on edge inputs (very long text, many pages) | R1.2 fails loudly; drop or adjust the case and record why |
| All documents share one layout, so we measure one template | R1.5 requires 2 layouts, split 15/15 |

## Open questions

- ~~OQ-2.1 Nota de crédito in scope or negative~~ resolved 2026-09-14: **out of scope, as a negative**. Notas de crédito/débito and factura M expect a failure with reason `unsupported_document_type` (distinct from `not_an_invoice`). They are tagged `unsupported_document` and their manifest `expected_outcome` is `explicit_failure`.
- ~~OQ-2.2 JPG and no-text-layer cases: part of the 30 or extra variants~~ resolved 2026-09-15: **they count toward the 30** as documents of their own, not as variants of other documents. Consequence for PRD 03 R5: path B (local text extraction) cannot read them, so they are explicit failures for path B by design. The path comparison reports them in their own group instead of mixing them into per-field deltas.
- New, resolved 2026-09-15: **B invoices under Ley 27.743 ("IVA Contenido")** are not rendered in synthetic B invoices — the templates have no field for it. A dedicated schema field is a PRD 04 candidate iteration if a real ticket needs it.
- New, resolved 2026-09-15: **FCE MiPyMEs (`tipo_cbte` 201 family)** stays outside the 30; recorded as a candidate negative for PRD 04.
- New, **open:** where a printed "IVA Contenido" on a *real* ticket goes in the hand-annotated ground truth. Affects only `ground_truth_real/`, decided when the photos arrive (`add-synthetic-dataset` task 8.1).
