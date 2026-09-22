## 1. Generator fix (tools/generate_invoices, own venv)

- [ ] 1.1 Record the starting state: run the generator test suite and note that `test_regeneration.py` fails on A03/A04/A07/A10 ground truth (the `148bac7` hand fix); verify by pasting the failing test names in the task note
- [ ] 1.2 Add per-letter `pricing` (`net` A, `gross` B and nota de débito B, `none` C and E) to `generate_params` and `Item` (design D1/D2), keeping every random draw in the same order; verify with `test_params.py` tests: a B item's net + VAT equals its printed line exactly, a B invoice's lines sum to its total, a C item has no rate and C total = lines, and A/E params for seeds 1001–1010 and 1023–1025 are equal to those produced before the change (snapshot taken first)
- [ ] 1.3 Make the issuer VAT condition per letter (C → Responsable Monotributo) in one function used by `render.py` and `visibility.py`, and pass the per-letter `imp_neto`/`imp_iva`/`imp_total` and item amounts to pyfepdf; verify with `test_visibility.py`: a C ground truth has `responsable_monotributo` and null item rates, a B consumidor final keeps its rates with VAT-included line amounts
- [ ] 1.4 Order `vat_breakdown` by the template's `IVA<rate>` field position (design D3); verify with a test that A03's regenerated breakdown matches the committed (hand-corrected) order, and that an unknown rate fails generation
- [ ] 1.5 Verify the printed order of `vat_breakdown` in `verify.py` (design D4); verify with a test that a reversed breakdown fails generation naming `vat_breakdown`, and that every other `test_verify.py` test still passes
- [ ] 1.6 Commit the generator changes (generation refuses dirty code); verify the generator suite passes except `test_regeneration.py`, which is expected to fail on the 16 documents until task 2.2

## 2. Regenerate the dataset (design D5)

- [ ] 2.1 Generate into a temporary directory and diff against `ground_truth/` with a throwaway script; verify the differing files are exactly B01–B07 and C01–C05 (ground truth + document) and `nota_debito_b.pdf`, and stop the change if anything else differs
- [ ] 2.2 Copy the 16 changed documents in, and update `manifest.jsonl`: new `generator_version` on every entry, refreshed `gt_check`/`pages`, review stamps reset to null only on the 16; verify `test_regeneration.py` and `test_composition.py` pass and the manifest lists exactly 16 unreviewed entries
- [ ] 2.3 Check the new ground truth arithmetic: for every in-domain invoice, A items = net and net + VAT = total; B/C/E lines = total; C issuer is monotributo; verify with a throwaway script over `ground_truth/*.json` (output in the task note), and the extractor's `pytest` (schema validation of every ground truth) passes
- [ ] 2.4 **User task:** review the 16 regenerated documents with the `review` checklist command and stamp them; verify no manifest entry has a null `reviewed_by`

## 3. Re-run the baseline (design D6; spend cap $3)

- [ ] 3.1 Run `python -m invoice_extractor.evaluate --path a --spend-cap 3` on the regenerated dataset and commit the run record; verify it is complete, carries the new generator SHA, and record measured cost/doc and p95 in design D6 in place of the estimate
- [ ] 3.2 Re-render `docs/quality-report.md` from the new run, keeping the path comparison section with a note that it was measured on the previous dataset version (generator `f7ff2e1`); verify the report renders offline with `python -m invoice_extractor.report_cli` and every headline number matches the run record
- [ ] 3.3 Rewrite `docs/failure-analysis.md` on the new run (categories, counts, examples, ranked hypotheses), keeping the planning note that hypothesis "B/C has no item VAT rate" is contradicted by B03/B06; verify every wrong field in the new run's comparison appears in it

## 4. Hand-off to stage 4

- [ ] 4.1 Update `add-validation-and-iterations`: design D5 refuses comparisons across generator versions, and task 0.1 points at the new baseline run ID; verify `openspec validate add-validation-and-iterations --strict` passes
- [ ] 4.2 Record in `docs/prd/02-dataset.md` (resolved decisions) the B/C pricing rule, the C issuer and the date; verify `openspec validate fix-synthetic-fiscal-consistency --strict` passes before archiving
