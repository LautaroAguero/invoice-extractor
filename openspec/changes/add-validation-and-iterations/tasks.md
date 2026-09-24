## 0. Prerequisite

- [ ] 0.1 Confirm the B/C generator-fix change is archived and its re-run v1 baseline is committed under `runs/`; verify the validator precondition by computing, for every in-domain `ground_truth/*.json`, items + other taxes = total when `net_amount` is null (a throwaway script, output pasted in the task note)

## 1. Business validation (PRD 04 R1; spec invoice-validation)

- [ ] 1.1 Create `validation.py` with the `Problem` model, the `validate(invoice, *, today)` entry point that concatenates checks in fixed order, and the tolerance helper (design D1); verify with tests: an empty invoice-level result for `A01` ground truth, tolerance 0.03 over 4 items passes and 0.05 fails, and an import-boundary test asserting the module imports nothing from `client`, `prompts`, `extraction` or `anthropic`
- [ ] 1.2 Implement V1 (mod-11 CUIT, issuer and customer when present) and V7 (point of sale 5, invoice number 8, CAE 14 digits); verify with corrupted-invoice tests (flipped CUIT digit, base whose digit would be 10, 13-digit CAE), each asserting exactly one problem on exactly that path
- [ ] 1.3 Implement V2 (items → net when net printed), V2b (per-line arithmetic) and V4 (VAT per rate from item bases, including a breakdown rate with no items); verify with corrupted-invoice tests (dropped item, misread quantity, VAT line off by 1.00, orphan rate) built from ground-truth fixtures
- [ ] 1.4 Implement V3 in both forms (WSFE formula with net printed; items + other taxes when not) and V6 (issue ≤ today, due ≥ issue, CAE expiry ≥ issue); verify with corrupted-invoice tests (total +1.00 on an A and on a C, CAE expiry before issue, issue date after `today`)
- [ ] 1.5 Implement V5 (A: customer CUIT, VAT present, item rates; B/C: no breakdown or VAT amount; C/E: no item rates; foreign currency ⇔ exchange rate; document code ↔ letter); verify with tests including a Factura B with item rates that passes (B03 shape), an A with null customer CUIT, and letter B with code 01
- [ ] 1.6 Add the ground-truth guard test: `validate` returns no problem for every in-domain invoice in `ground_truth/` with `today` = its issue date; verify it passes on the regenerated dataset

## 2. Model client (spec model-client, MODIFIED; design D3)

- [ ] 2.1 Accept `messages` (alternating turns, starting and ending with `user`) in `ModelClient.call` alongside `content`, raising before any request on a malformed conversation; add `raw_text` to `CallFailure` for `invalid_output`; verify with fake-SDK tests: the three-turn request is sent in order, a conversation ending in `assistant` sends nothing, and an `invalid_output` failure carries the raw text
- [x] 2.1b Raise instead of recording when a 400 says the account's credit balance is too low or names a billing problem, so a run aborts like it does on an auth error (done 2026-09-22, ahead of this change: run `20260922-195941` finished "complete" with 20 such api_errors); verified by client, execute and CLI tests with no API key
- [ ] 2.2 Count transport requests per call with an `http_client` request hook and a `ContextVar` set inside `call`; add `CallRecord.transport_requests` (defaulting to 1 when read from older records); verify with `MockTransport` tests: 529-then-200 reports 2, two concurrent calls where only one is retried report 2 and 1, and a fake SDK without the hook reports 1

## 3. Corrective retries (PRD 04 R2; spec corrective-retries; design D2)

- [ ] 3.1 Write `prompts/correct_invoice/v1.md` (list the problems; correct only values that are printed; return a failure if the document does not allow a consistent extraction) and a loader that renders it with a problem list; verify with a test that renders two problems and that a missing version raises `PromptNotFoundError`
- [ ] 3.2 Implement `processing.py`: `ProcessedDocument`, `Attempt`, the four final-outcome types, and `process_document` with the loop from design D2 and `1 <= max_attempts <= 5`; verify with fake-SDK tests: valid on attempt 1; success on attempt 2 with the problems and the previous output present in request 2; always-invalid hits cap 3 with exactly 3 requests and ends `ValidationFailed` carrying the problems; `not_an_invoice` makes one call and no validation; truncated makes one call and no correction; `invalid_output` enters correction; cap 0 and 6 are rejected before any request
- [ ] 3.3 Sum cost and latency over attempts and expose corrective attempt and transport request counts on `ProcessedDocument`; verify with a test where two calls cost $0.04 and $0.05 and the document reports $0.09 and 2 attempts, plus one with a transport retry reporting 1 attempt and 2 transport requests
- [ ] 3.4 Support `validate_on=False` (first extraction is final, no corrective attempt); verify with a fake-SDK test that an invoice failing V3 is accepted after 1 attempt
- [ ] 3.5 Route `extract_one` through `process_document`, adding an attempts line and the problem list on validation failure to the printed summary; verify existing `tests/test_cli.py` still passes and a new test shows a validation failure summary with the same exit-code contract

## 4. Evaluation (spec invoice-evaluation, MODIFIED; design D4)

- [ ] 4.1 Extend `RunConfig`, `DocumentResult` and `Aggregates` to format v2 (attempts, final kind, validation, correction prompt version, max attempts, measurement rules version, per-check counts, documents retried, validation rejections, transport retries) with a before-validator migrating v1 records; verify with a test that loads the committed stage 3 baseline run and asserts the rendered report equals a snapshot taken before this change
- [ ] 4.2 Make `execute` call `process_document` through both ingestion paths (path B's text block as the first user turn), score the final accepted invoice only, and map `ValidationFailed` to `explicit_failure`; verify with fake-SDK tests: a document fixed on attempt 2 is scored on its second invoice, a document hitting the cap counts as a false rejection with no field-precision contribution, and the spend cap still stops the run
- [ ] 4.3 Add the report's validation section (failures per check over attempts, documents retried as a Wilson rate flagged at ≥30%, validation rejections, transport retries apart) and make cost/doc and latency include every attempt, in terminal and markdown; verify with fixture-run-record tests for the "V3 2, V1 1" scenario and for 10/30 retried being flagged, and that a validation-off run renders no validation section
- [ ] 4.4 Add `--model`, `--max-attempts` and `--no-validation` to `evaluate`, and the new run ID format `{ts}-{model_short}-{prompt}-path_{p}-{sha}`; verify with CLI tests using a fake client: an unknown model fails with exit 2 before any request, the chosen model and settings land in the run config, and two runs differing only in model get different IDs

## 5. Iteration protocol (PRD 04 R3, R4, R5.1; spec iteration-protocol; design D5)

- [ ] 5.1 Implement `evaluation/version_comparison.py` (refuse on differing document IDs or measurement-rules version; McNemar, per-field and invented-value deltas, cost/doc and p95 for both, "clears noise"/"within noise" statement) and its markdown rendering; verify with fixture run records: a 1-of-30 difference is "within noise" with its p-value, and a manifest mismatch raises naming the mismatch
- [ ] 5.2 Implement `docs/iterations/versions.toml` loading and `python -m invoice_extractor.iterations` rendering the log table and the model comparison table into `README.md` between markers, with `--check` for staleness; verify with a test over fixture run records and a registry, and that `--check` fails after editing a number in the README
- [ ] 5.3 Create the `README.md` skeleton (title, one-line problem, iteration log markers, stage 5 placeholder note) and `docs/iterations/v1.md` pointing at the prerequisite baseline run; verify `python -m invoice_extractor.iterations --check` passes with the single v1 row

## 6. Iterations (spend: design D6 estimates, USD 10 total budget)

- [ ] 6.1 v2 · validation + corrective retries: commit `docs/iterations/v2.md` (hypothesis, evidence, and the note that failure-analysis hypothesis 2 is contradicted by B03/B06) and its registry entry, then run `evaluate --spend-cap 3`; verify the run record is committed, the paired comparison vs v1 is in the log, and the recorded cost is checked against the D6 estimate
- [ ] 6.2 v3 · prompt `extract_invoice/v2` (drafted 2026-09-24 ahead of this change, for hand exploration in the UI; it has no hypothesis file and no run record yet, so it is not an iteration until this task runs it) (absent IVA column → `vat_rate` null; rule only, no evaluation document quoted): commit the hypothesis first, then run with `--spend-cap 3`; verify run record, paired comparison vs v2, and whether B05's invented values are gone, with the noise statement
- [ ] 6.3 v4 · `claude-haiku-4-5` on the best of v2/v3: commit hypothesis, run with `--spend-cap 3`; verify run record and paired comparison
- [ ] 6.4 v5 · `claude-opus-5` on the best of v2/v3: commit hypothesis, run with `--spend-cap 6` only if the stage's recorded spend plus the D6 estimate stays ≤ USD 10 (otherwise log that the budget stopped it); verify run record, paired comparison and the model comparison table
- [ ] 6.5 Render the final log and model table into `README.md`, add the stage's total recorded spend next to the log, and update design D6 with measured cost/latency replacing the estimates; verify `python -m invoice_extractor.iterations --check` passes and at least one row states a within-noise result if that is the case

## 7. Close-out

- [ ] 7.1 Run the final configuration once over `ground_truth_real/` and record in the real-set report (git-ignored) how many tickets fail V3/V5 on "IVA Contenido", as input for the PRD 04 R6 contained-taxes lever; verify the output lives under `runs/real/` and nothing real is committed
- [ ] 7.2 Check PRD 04 acceptance criteria one by one (≥5 checks with corrupted tests, capped retries with explicit failure, negatives as explicit failures, ≥3 logged versions with paired comparisons, cost over all attempts, an honest within-noise row) and tick them in `docs/prd/04-iterate-with-evidence.md`; verify `pytest` passes with no API key set
