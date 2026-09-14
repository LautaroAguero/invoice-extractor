# PRD 02 · Dataset

Status: draft · Stage 2 of 5 · Depends on: PRD 01 (schema), [measurement rules](../measurement-rules.md) · Course estimate: ~3 h

## Why

Without a labelled dataset, nobody can say how good the extractor is, and every later change is a guess. This stage produces the ground truth before anything is optimized. If we optimize before we can measure, we will "fix" things that were not broken.

## Scope

**In**
- A seeded, reproducible synthetic invoice generator in `tools/generate_invoices/`, built from the spike.
- ≥30 documents with ground truth in `ground_truth/`, ≥8 of them hard cases.
- A dataset manifest describing each document.
- A human review pass over every document.

**Out**
- Real invoices of any kind.
- The evaluation harness (PRD 03).
- Prompt or schema changes driven by what the dataset reveals (PRD 04).

## Requirements

### R1 · Generator

- **R1.1 Reproducible.** Documents are generated from a seed and a parameter set. The same seed produces the same PDF and the same ground truth. The generator version (git SHA and pyafipws pin) is recorded.
- **R1.2 Fails loudly.** It runs with `LanzarExcepciones = True`. A rendering error aborts that document; it never writes ground truth next to a broken PDF.
- **R1.3 Valid synthetic identifiers.** CUITs carry a correct mod-11 check digit, except where a case deliberately tests an invalid one (that case must be tagged). CAE numbers have 14 digits.
- **R1.4 Arithmetic consistent by construction.** Items sum to net, VAT per rate matches its base, and net plus VAT plus other taxes equals the total. Values are exact decimals with explicit rounding.
- **R1.5 Variation, not one template.** It covers invoice types A, B, C and E, at least 3 visual layouts (edited pyfepdf CSV templates), 1 to 30+ items, mixed VAT rates (21% and 10.5%), discounts, other taxes, and optional fields present or absent.
- **R1.6 Isolated.** It has its own venv and requirements, is GPL-3.0 and is never imported by the extractor package.

### R2 · Hard cases (≥8)

Each hard case is tagged in the manifest. Required coverage:

| Tag | What | How it is produced |
|---|---|---|
| `multi_page` | ≥2 pages | Enough items to overflow `lineas_max` |
| `foreign_currency` | Factura E in USD with exchange rate | `moneda_id` DOL + rate |
| `skewed_scan` | Rotated, noisy raster | Rasterize, rotate 2–5°, add noise; delivered as PDF with **no text layer** |
| `image_input` | JPG instead of PDF | Same degradation pipeline, saved as JPG (covers the second input format) |
| `missing_optional` | Customer CUIT, address or due date absent | B to final consumer, etc. |
| `not_an_invoice` | Similar-looking non-invoice (remito, presupuesto) | Edited template without CAE/VAT, "no válido como factura" |
| `dense_table` | Long descriptions and overlapping columns | Long `ds` text; the known IVA/price column overlap |

Proposed composition (to confirm): 20 regular (A ×8, B ×7, C ×5) plus 10 hard (multi_page ×2, foreign_currency ×2, skewed_scan ×2, image_input ×1, missing_optional ×1, not_an_invoice ×2).

### R3 · Ground truth

- **R3.1 Visible truth rule.** Ground truth is **what is visible on the rendered document**, not the dict fed to the generator. If the template truncates a description or reformats a number, the ground truth follows the document.
- **R3.2 Schema-shaped.** Ground truth for `expected_outcome = extracted` validates against the PRD 01 result schema. Ground truth for `not_an_invoice` records the expected failure, not an invoice.
- **R3.3 Format follows the measurement rules.** Absent optional fields are explicit `null` (never omitted keys), because `null`=`null` scores as correct. Items keep document order, because items are matched by position. Amounts are exact decimal strings, because amounts are compared exactly.

### R4 · Manifest

`ground_truth/manifest.jsonl`, one line per document with:
- `id`, `file`, `format` (pdf/jpg)
- `seed`, `generator_version`
- `invoice_type`, `tags`
- `expected_outcome` (`extracted` or `explicit_failure`)
- `reviewed_by`, `reviewed_at`

### R5 · Human review

- **R5.1** Every document is opened and compared by eye against its ground truth. With 30 documents this takes minutes, and it is the only defense against R3.1 violations.
- **R5.2** For documents with a text layer, an automated check confirms that key values (total, CUITs, invoice number, CAE) appear in the extracted text in their printed format. It flags mismatches for review; it does not replace review.

### R6 · Contamination rule

Documents used as few-shot examples in prompts (PRD 04) are generated with seeds disjoint from the evaluation set and never taken from `ground_truth/`.

## Acceptance criteria

- [ ] `ground_truth/` holds ≥30 documents, each with a ground truth JSON and a manifest entry.
- [ ] ≥8 documents carry hard-case tags covering every row of the R2 table.
- [ ] At least one document is a JPG and at least one PDF has no text layer.
- [ ] Regenerating from the manifest seeds reproduces identical ground truth.
- [ ] Every manifest entry has `reviewed_by`/`reviewed_at` filled in.
- [ ] Every `extracted` ground truth validates against the result schema, and every valid-case CUIT passes the check digit.
- [ ] No real person or company data appears anywhere in the dataset.

## Risks

| Risk | Mitigation |
|---|---|
| Synthetic data is too clean, so baseline precision is near 100% and there is nothing to iterate on | Hard cases, degradation and dense tables are mandatory, not optional; README declares the synthetic limitation |
| Ground truth drifts from what is rendered (truncation, formatting) | R3.1 + R5 |
| pyfepdf breaks on edge inputs (very long text, many pages) | R1.2 fails loudly; drop or adjust the case and record why |
| All documents share one layout, so we measure one template | R1.5 requires ≥3 layouts |

## Open questions

- **OQ-2.1** Is a nota de crédito in scope (a fiscal document shaped like an invoice) or a `not_an_invoice` negative?
- **OQ-2.2** Do the JPG and no-text-layer cases count toward the 30, or are they extra variants of existing documents? Variants give a cleaner paired comparison of ingestion paths.
