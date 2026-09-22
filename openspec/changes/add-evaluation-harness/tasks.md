## 1. Scaffolding

- [x] 1.1 Add `pdfplumber` to `[project.dependencies]` in `pyproject.toml` (design D5); verify `pip install -e .` succeeds and `import pdfplumber` works with no API key set
- [x] 1.2 Create the `src/invoice_extractor/evaluation/` package (empty modules per design D1: `manifest.py`, `compare.py`, `stats.py`, `run_record.py`, `execute.py`, `report.py`, `ingestion.py`, `path_comparison.py`) and add `runs/real/` to `.gitignore` next to the existing `ground_truth_real/` line; verify `pytest` still passes and `git status` shows the new gitignore line

## 2. Manifest loading

- [x] 2.1 Implement `manifest.py`: typed `DocumentEntry`/`Manifest` covering every field used later (`id`, `file`, `format`, `source`, `tags`, `expected_outcome`, `expected_reason`), loaded from a JSONL path; verify with a test that loads `ground_truth/manifest.jsonl` and asserts count 30 (the 2 real documents live in `ground_truth_real/manifest.jsonl`) and that `A05` has tag `skewed_scan`

## 3. Statistics (no model calls)

- [x] 3.1 Implement `wilson_interval(k, n, confidence=0.95)` (design D4); verify against at least 3 published reference values (e.g. k=27,n=30) with an absolute tolerance test
- [x] 3.2 Implement `mcnemar_exact(b, c)` two-sided exact test on discordant pairs (design D4); verify against a known reference p-value and against the symmetric case `b == c`

## 4. Comparison and scoring (PRD 03 R2, `docs/measurement-rules.md`)

- [x] 4.1 Implement normalization per §4 (Decimal exact, ISO date, digits-only identifiers, casefold/whitespace-collapsed text) as one function per kind, keyed by a field-name/type table built from `Invoice`'s Pydantic fields (design D3); verify with unit tests for each kind, including the `"150000.00" == "150000"` and CUIT-with-hyphens cases
- [x] 4.2 Implement scalar field comparison per §2 (correct/wrong/missed/invented per the null-handling table); verify with a test for every row of the §2 table
- [x] 4.3 Implement position-matched list comparison per §3 (`_exact` and `_per_entry` for `items`, `vat_breakdown`, `other_taxes`, extra-entry counting, order-only-mismatch detection); verify with tests: a skipped early row cascades every later entry to wrong, an extra `vat_breakdown` entry on an empty-ground-truth list counts as an extra entry, and a reordered-but-identical list is flagged order-only
- [x] 4.4 Implement document-level outcome classification per §1 (extraction / false rejection / false acceptance / correct rejection) from an `expected_outcome` and an actual `Extracted`/`Failed` result; verify with one test per cell of the §1 table
- [x] 4.5 Wire 4.1-4.4 into one `compare(prediction: ExtractionResult, ground_truth: Invoice | None, expected_outcome, expected_reason) -> ComparisonResult`; verify with an end-to-end test using the `A01` ground truth JSON fixture with a hand-built matching and a hand-built mismatching prediction

## 5. JPG support in extraction (PRD 03 R5.1; invoice-extraction spec, MODIFIED)

- [x] 5.1 Add `image_block(path)` alongside `pdf_document_block` and dispatch on suffix in `extract_document` (`.pdf` -> document block, `.jpg`/`.jpeg` -> image block, else `UnsupportedInputError`) (design D6); verify with fake-client tests: a JPG input produces a request whose user turn contains an image block, and a `.txt` input is still rejected with zero model calls
- [x] 5.2 Update the `invoice-extraction` capability's existing PDF-only test/scenario coverage to include the JPG case; verify `pytest tests/test_extraction.py` passes

## 6. Run record (PRD 03 R1)

- [x] 6.1 Implement `RunConfig` (model ID, prompt version, schema hash of `transform_schema(ExtractionResult)`, `anthropic`/`pydantic` versions via `importlib.metadata`, ingestion path, generator version read from the manifest, git SHA via `git rev-parse HEAD`, timestamp, `complete: bool`) and `DocumentResult` (extraction record + comparison result) as frozen Pydantic models; verify with a round-trip test: build one, serialize, deserialize, fields equal
- [x] 6.2 Implement `write_run_record(dir, run_id, config, aggregates, results)` writing `<run_id>.json` (config + aggregates) and `<run_id>.jsonl` (one `DocumentResult` line per document), and `read_run_record(dir, run_id)` reading them back; verify with a round-trip test over a small synthetic set of results, and a test that a real-set run written under `runs/real/` never touches the top-level `runs/` path

## 7. Execution (PRD 03 R4)

- [x] 7.1 Implement `execute(manifest, client, prompt, *, max_concurrency, spend_cap_usd) -> RunRecord` running `extract_document`/path-A ingestion per document under an `asyncio.Semaphore`, comparing each result via `compare()`, and accumulating cost under a lock (design D8); verify with a fake client and small concurrency (e.g. 3) that all documents complete and results are independent per document
- [x] 7.2 Implement the spend cap: stop starting new calls once the running total would exceed `spend_cap_usd`, let in-flight calls finish, mark the resulting record `complete=False`; verify with a mocked client returning a fixed cost per call that a cap set below the full-dataset cost stops the run early and the record is marked incomplete (PRD 03 acceptance criterion)
- [x] 7.3 Verify one document's `api_error`/`truncated`/`refused` outcome does not abort the run: a fake client scripted to fail on one specific document still returns a full `RunRecord` with every other document's outcome populated

## 8. Report (PRD 03 R3, `invoice-evaluation` spec)

- [x] 8.1 Implement `report(run_record) -> ReportSections` computing: correct-outcome rate + components (extraction rate, false rejections, correct rejections, false acceptances, reason agreement), invented/missed counts, per-field precision (with list `_exact`/`_per_entry`), per-tag breakdown, attempts distribution, cost/latency summary — every rate paired with its Wilson interval via `stats.wilson_interval`; verify with a test built from a hand-constructed `RunRecord` fixture whose expected numbers are computed by hand
- [x] 8.2 Mark the worst field automatically (lowest precision among scored fields, ties broken by field name for determinism); verify with a fixture where one field is deliberately the worst
- [x] 8.3 Implement the real-set section: documents with manifest `source` `real` excluded from every headline count/rate and rendered in their own labeled section; verify with a fixture mixing synthetic and real documents that the real ones never appear in the `DOCUMENTS` line
- [x] 8.4 Implement `render_terminal(sections)` and `render_markdown(sections)` matching the PRD 03 R3 report shape; verify with a snapshot test on the fixture from 8.1
- [x] 8.5 Reject an incomplete run record (`complete=False`) at report time with a clear error instead of a partial report; verify with a test

## 9. Ingestion path B (PRD 03 R5.1, R5.3; `ingestion-path-comparison` spec)

- [x] 9.1 Implement `extract_text_pages(path) -> str | None` using `pdfplumber.open(path).pages[i].extract_text()` (default mode, all pages joined), returning `None` when every page yields no text; verify with a test over a `ground_truth/` PDF with a text layer (non-`skewed_scan`) that text is non-empty, and over `A05.pdf` (`skewed_scan`) that it returns `None`
- [x] 9.2 Implement `extract_document_path_b(path, ...)`: for a PDF with extractable text, call the model with a text content block; for a PDF with no text layer or any JPG, return an explicit failure without calling the model (R5.3); verify with fake-client tests: a text-bearing PDF sends a text block, `A05.pdf` and a `.jpg` input both produce an explicit failure with zero model calls

## 10. Path comparison (PRD 03 R5.2, R5.4)

- [x] 10.1 Implement `compare_paths(manifest, client, prompt, ...)` running both `execute()` (path A) and a path-B equivalent over the same documents, separating the no-text/image-only coverage group (R5.3) from the paired precision comparison; verify with a fake client and a small manifest that both run records come back and the coverage group contains exactly the `skewed_scan`/`image_input` documents
- [x] 10.2 Implement the paired result: `stats.mcnemar_exact` on per-document correct-outcome agreement/disagreement, per-field precision deltas over documents both paths extracted, and the result table (precision, invented values, cost/doc, p95 latency per path) naming a winner and its trade-off; verify with a fixture where path A and path B disagree on a known set of documents that the McNemar counts match a hand calculation

## 11. CLI entry points

- [x] 11.1 Implement `python -m invoice_extractor.evaluate [--dataset ground_truth|ground_truth_real] [--spend-cap N] [--max-concurrency N] [--path a|b|compare]` writing a run record to `runs/` (or `runs/real/` for the real dataset) and printing the terminal report; verify with a fake-client integration test (no network) that it exits 0 and a run record file exists
- [x] 11.2 Implement `python -m invoice_extractor.report_cli <run_id> [--dataset runs|runs/real] [--markdown out.md]` re-rendering a saved run record with no client constructed at all; verify with a test that it runs successfully with `ANTHROPIC_API_KEY` unset and no `ModelClient` import triggers a network call

## 12. Baseline run and failure analysis (manual, real API; not part of pytest)

- [x] 12.1 Run `python -m invoice_extractor.evaluate` over `ground_truth/` with `--path compare` (both ingestion paths) and a spend cap comfortably above the estimated cost (design D7); verify the run completes (`complete=True`) and commit the resulting `runs/<run_id>.json` + `.jsonl` (synthetic data only, PRD 03 R1.3)
- [ ] 12.2 Run the same command over `ground_truth_real/`; verify the run record is written under `runs/real/` and `git status` shows it untracked
- [x] 12.3 Render and commit the markdown report from the baseline run; verify it matches the PRD 03 R3 shape and the real-set section is present and separate
- [x] 12.4 Write `docs/failure-analysis.md` from the baseline comparison output: classify every wrong field, one example each, ranked hypotheses for PRD 04 with evidence pointers (PRD 03 R6); verify every PRD 03 acceptance-criteria checkbox that names this file is satisfied by inspection
- [x] 12.5 Replace the ESTIMATED figures in design.md D7 with the measured tokens/cost/latency from the baseline run, labelled with date and model

## 13. Wrap-up

- [x] 13.1 Run `pytest` with `ANTHROPIC_API_KEY` unset; verify the full suite passes with no network access
- [x] 13.2 Run `git status`; verify no `.env`, no `ground_truth_real/` content and no `runs/real/` content is staged, and that only the intended `runs/` baseline files and source changes are
