## Why

Planning stage 4 (`add-validation-and-iterations`) surfaced three defects in the synthetic dataset, and the stage 4 business validator cannot run on the dataset until they are fixed:

1. **B and C totals are unexplained by the print.** The generator computes every letter's total as net + VAT (`tools/generate_invoices/generator/params.py:120`). A Factura B or C prints neither net nor VAT, so its total matches nothing on the page. For example, B01's items sum to 1,047,400.00 and its total is 1,223,632.00. In a real Factura B the prices include VAT, so the lines add up to the total. A Factura C is issued by a monotributista and carries no VAT at all. The stage 4 V3 check would reject all 15 B/C documents as false rejections.
2. **A Factura C is issued by a Responsable Inscripto.** The issuer header is fixed to "IVA Responsable Inscripto" for every letter (`render.py`, `params.py:45`). A C comes from a Responsable Monotributo, so this is the same fiscal inconsistency as the VAT, fixed in the same regeneration.
3. **The generator writes `vat_breakdown` in the wrong order.** Commit `148bac7` hand-corrected A03, A04, A07 and A10 to the printed order, but the generator still emits first-seen-rate order. Regenerating the dataset would silently undo that fix, and the committed ground truth no longer matches its generator. The regeneration test, which requires byte-identical ground truth, cannot pass today.

This change fixes the generator, regenerates the dataset, and re-runs the v1 baseline that stage 4 will compare against. The user chose this option on 2026-09-22 over limiting V3 to letters A and E.

PRD: PRD 02 · Dataset (R1 composition unchanged, R3.1 visible-truth rule, R3 ground truth verification, R5 reproducibility, human review) and PRD 03 R1/R3/R6 for the re-run baseline and its documents. Open questions: none open. PRD 02's "IVA Contenido" decision stays as it is: synthetic B invoices still print no "IVA Contenido" line (the templates have no field for it).

## What Changes

- **Factura B:** the printed unit price and line amount include VAT. The printed total is the sum of the lines. Net and VAT are still computed exactly and passed to the renderer as WSFE requires, but they are not printed. When the customer is a consumidor final, the per-item VAT rate still prints and stays in the ground truth.
- **Factura C:** no VAT. Items carry no VAT rate, and the total is the sum of the lines. The issuer prints as "Responsable Monotributo", and its ground truth `issuer.vat_condition` becomes `responsable_monotributo`.
- **Nota de débito B (negative):** follows the Factura B pricing rule, because it prints the same letter. Its ground truth stays a failed result; only its PDF changes.
- **`vat_breakdown` order:** follows the printed order, which is the template's vertical position of each `IVA<rate>` field. The field check verifies the printed order of `vat_breakdown` lines, so an order defect fails generation instead of reaching the ground truth.
- **Regeneration:** the dataset is regenerated with the same seeds and the same random-number sequence. A and E documents and the other four negatives come out byte-identical to the committed files (ground truth, clean PDFs, degraded pixels). Only the 15 B/C documents and the nota de débito B change. Only those 16 are reviewed again by a human, and only their review stamps are reset.
- **Re-run baseline v1:** Sonnet 5, prompt v1, path A, over the regenerated dataset. Re-render `docs/quality-report.md` and update `docs/failure-analysis.md` on the new run. The stage 3 run records and the path A vs path B comparison stay as they are. They are labeled as measured on the previous dataset version and are not compared with the new runs.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `invoice-dataset`: the arithmetic-consistency requirement now depends on the invoice letter (A: items → net → net + VAT = total; B: lines include VAT and add up to the total; C: no VAT; E: lines add up to the total). Verification also checks the printed order of `vat_breakdown`. A Factura C's issuer is a Responsable Monotributo.

## Impact

- Generator code (GPL-3.0, own venv): `tools/generate_invoices/generator/params.py`, `render.py`, `visibility.py`, `verify.py` and their tests.
- Committed data: `ground_truth/` B01–B07, C01–C05, `nota_debito_b.pdf`, and `manifest.jsonl`. Every entry gets the new generator `git_sha`; the 16 changed documents get new review stamps.
- Committed measurement: a new v1 run record in `runs/`, a re-rendered `docs/quality-report.md` and an updated `docs/failure-analysis.md`. Spend: one path A run, measured at $1.13 on the old dataset; cap $3.
- Stage 4 planning: `add-validation-and-iterations` uses this re-run as its baseline. Its version comparison must also refuse runs over different generator versions (a one-line addition to that change's design D5, made here).
- No extractor code changes.
