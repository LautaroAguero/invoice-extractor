## 1. Setup

- [ ] 1.1 Add `pdfplumber` (with its `pypdfium2`) and `pytest` to `tools/generate_invoices/requirements.txt`, pinned. Verify the install succeeds in the generator venv and `pip freeze` shows both pinned versions.
- [ ] 1.2 Add `ground_truth_real/` to `.gitignore` before creating the directory. Verify `git check-ignore -v ground_truth_real/manifest.jsonl` reports the rule.
- [ ] 1.3 Create the generator test layout (`tools/generate_invoices/tests/`) with one placeholder test. Verify `pytest` passes from the generator venv, and that the extractor's `pytest` (repo root) does not collect generator tests.

## 2. Templates

- [ ] 2.1 Copy upstream `plantillas/factura_qr.csv` (pyafipws `d595b07`) to `templates/qr_base.csv`, applying the spike's edits (no pyafipws logo, local image paths). Verify by rendering the spike Factura A parameters on it and checking by eye that the values and the QR render.
- [ ] 2.2 Add the currency and exchange-rate fields (design D8) to `qr_base.csv`. Verify by rendering a Factura E with `moneda_id` `DOL` and a rate, and checking that "USD" and the rate appear in the pdfplumber text.
- [ ] 2.3 Create `templates/qr_variant.csv` from `qr_base.csv` with different item-table labels and the unit price and line amount columns swapped (design D4). Verify by rendering the same Factura A on both layouts and checking by eye that no field overlaps or is cut. If editing exceeds ~1 h, keep labels only and record that in design D4.
- [ ] 2.4 Create the presupuesto template from `qr_base.csv` (title "Presupuesto", no CAE, QR or barcode, legend "Documento no válido como factura"). Verify by rendering it and checking by eye that no CAE or fiscal code is printed.

## 3. Verify pyfepdf behavior before relying on it

- [ ] 3.1 Render one clean document per case family on `qr_base`: A, B to a responsable inscripto, B to a consumidor final, C, E. Verify each against the design D3 visibility table by eye, and record any deviation in D3 before task 4.2.
- [ ] 3.2 Render a multi-page A (more items than `lineas_max - 1`) with one long description. Verify that totals appear only on the last page, that earlier pages print "Subtotal:", and whether the description wraps or truncates; record the result in design D3.
- [ ] 3.3 Render the negatives: `tipo_cbte` 3, 7, 4 and 91. Verify the printed titles ("Nota de Crédito", "Nota de Débito", "Recibo", "Remito") and letters (A, B, A, R) by eye; record deviations in design D5.
- [ ] 3.4 Pin `fpdf`'s creation timestamp (design D6) and render the same document twice. Verify the two PDFs are byte-identical (hash comparison); if other non-deterministic bytes remain, record their source in D6.

## 4. Generator core

- [ ] 4.1 Implement seeded parameter generation: parties, items, rates, dates, amounts; CUITs with legal-entity prefixes and a valid check digit; 14-digit CAE; exact-decimal arithmetic. Verify with generator tests: the same seed gives equal parameters, every CUIT passes mod-11 with prefix 30/33/34, and totals close exactly.
- [ ] 4.2 Implement the visibility map (design D3, as confirmed in task 3) that turns parameters into ground truth. Verify with generator tests for A, B responsable inscripto, B consumidor final without identification, C and E: `null` versus value per field, lists in document order, `currency` convention.
- [ ] 4.3 Implement the printed-format rules and the field-by-field verification against pdfplumber text with whitespace collapsed. Verify with generator tests: a correct document passes and records checked/skipped counts, and a ground truth with one altered amount fails naming that field.
- [ ] 4.4 Wire render → verify → write so that nothing is written when rendering or verification fails. Verify with a generator test that forces a rendering error and a verification failure and asserts that no PDF, JSON or manifest entry was written.
- [ ] 4.5 Implement negative rendering (design D5), with failed-result ground truth carrying the expected reason and `gt_check` `null`. Verify with generator tests that each negative's ground truth is a failed result with the right reason.

## 5. Degradation

- [ ] 5.1 Implement rasterize → rotate → noise → blur with the case RNG (design D7). Choose and freeze the noise and blur parameters on the first render so the text stays readable. Verify by eye on one render, and with a generator test that degrading the same clean PDF twice with the same seed gives identical pixels.
- [ ] 5.2 Implement the `skewed_scan` PDF output (fixed `creationDate`/`modDate`) and the `image_input` JPEG output (quality 70). Verify with generator tests that pdfplumber returns no text from the `skewed_scan` PDF, and that the manifest degradation entry carries the clean source hash and every parameter.

## 6. Case list and manifest

- [ ] 6.1 Write `cases.py` with the 30 cases from design D9 (ids, seeds 1001–1030, kind, letter, layout, tags, flags). Verify with the composition check from 6.3.
- [ ] 6.2 Implement the manifest writer with every field in the spec (including `source`, `printed_letter`, `pages`, `degradation`, `expected_reason`, `gt_check`) and `generator_version` (git SHA, pyafipws commit, library versions). Verify with a generator test that an entry for an A, a degraded document and a negative has every key, with `null` where it does not apply.
- [ ] 6.3 Implement the composition check (30 documents; counts per kind, letter and layout; required tags; exactly 4 degraded; 15/15 split). Verify with generator tests that the real case list passes, and that a list with one case removed or one tag missing fails with a message.
- [ ] 6.4 Implement the review subcommand that sets `reviewed_by`/`reviewed_at` for one document and prints that document's `null` fields as a review checklist. Verify with a generator test on a temporary manifest.

## 7. Generate and review the dataset

- [ ] 7.1 Generate the 30 documents into `ground_truth/`. Verify that generation exits cleanly, every in-domain document passed verification, and the composition check passes.
- [ ] 7.2 Regenerate into a temporary directory from the manifest. Verify byte identity for ground truth and clean PDFs, and pixel identity for degraded documents.
- [ ] 7.3 Add an extractor test (`tests/test_dataset.py`, no API, no change to `src/`) that validates every `ground_truth/*.json` against the extraction result schema, and every in-domain CUIT against mod-11. Verify that `pytest` at the repo root passes with the API key unset.
- [ ] 7.4 Human review of all 30 documents against their ground truth, using the review checklist from 6.4 (user task). Verify that every manifest entry has `reviewed_by` and `reviewed_at`, and that any correction went through the generator, never through hand-edited JSON.

## 8. Real set

- [ ] 8.1 Resolve the design Open Question ("IVA Contenido" on real tickets) with the user after inspecting the two photos. Verify by recording the decision in design D10.
- [ ] 8.2 Store the two photographed B tickets (personal data covered) and hand-annotated ground truth in `ground_truth_real/`, with a manifest in the shared format (`source` `real`). Verify by running `tests/test_dataset.py` with the real set present: it validates the real ground truth too and is skipped when the directory is absent. Verify `git status` shows nothing under `ground_truth_real/`.

## 9. Documentation and cleanup

- [ ] 9.1 Update PRD 00: the data decision (30 synthetic for metrics, plus a separate git-ignored real set) and the non-goals. Verify by review against the proposal.
- [ ] 9.2 Update PRD 02 to match this change:
  - R1.1: tiered reproducibility contract.
  - R1.5: 2 layouts, with the reason.
  - R2: the composition is fixed, including `unsupported_document`.
  - R4: expanded manifest.
  - R5.2: field-by-field check.
  - Scope: the real set.
  - Record the "IVA Contenido" and FCE decisions.

  Verify by review against the spec and design D3–D10.
- [ ] 9.3 Update PRD 03 (report: a reason-agreement line for negatives, and a separate real-set section outside headline metrics) and PRD 04 (candidate iterations: a dedicated "IVA Contenido" field, FCE as a negative, a third layout). Verify by review against the proposal's open-questions table.
- [ ] 9.4 Update the data paragraph of `openspec/config.yaml` (synthetic metrics plus a git-ignored real set). Verify that the YAML parses and the context no longer says the data is 100% synthetic without qualification.
- [ ] 9.5 Remove `spike_factura_a.py` and the barcode `factura.csv`, or reduce them to a note, once the generator renders the spike's Factura A on `qr_base`. Verify that `tools/generate_invoices/` has no dead entry point and its docstrings point to the generator.
