## Why

Structured outputs guarantee shape, not truth: stage 3 can say how often the extractor is right against ground truth, but at run time nothing checks whether an extracted invoice is internally consistent, and nothing recovers when it is not. This change implements PRD 04 · Iterate with evidence: a business validator that exploits the invoice's own redundancies, corrective retries with a hard cap, and a measured iteration protocol whose log is the stage's portfolio artifact.

Requirement IDs covered: PRD 04 R1 (R1.1, R1.2), R2 (R2.1–R2.5), R3 (R3.1–R3.6), R4, R5.1 (model comparison). R5.2 (Batch API) and R5.3 (prompt caching) stay optional and out of this change's required tasks; R6 levers are candidates, not commitments.

Open questions this change depends on, all resolved with the user on 2026-09-22:
- **OQ-4.1** (rounding tolerance) — resolved: the tolerance of a check is 0.01 × the number of independently rounded amounts it sums (±0.01 × lines for items → net; ±0.01 for a single line product).
- **OQ-4.2** (Factura A without customer CUIT) — resolved: an ordinary validation problem. It enters the corrective retry (it may be a misread); if it survives the attempt cap, the document ends in an explicit failure carrying the problem, ready for human review.
- **OQ-4.3** (stopping condition) — resolved: at least 3 versions after the baseline (the PRD minimum) and a total iteration budget of USD 10. Stop when both are met or the budget is spent.
- **R5.1 in scope** — resolved: compare Haiku 4.5 and Opus 5 against Sonnet 5.

**Prerequisite (separate change, applied first):** the 15 synthetic Factura B and C documents print a total that no printed amount explains (the generator adds hidden VAT: `tools/generate_invoices/generator/params.py:120`; e.g. B01 items sum 1,047,400.00, total 1,223,632.00), and a Factura C carrying VAT is fiscally wrong. V2/V3 would reject all 15 as false rejections. The user chose to fix the generator (B line amounts include VAT, C carries no VAT, items = total on both), regenerate those documents and their ground truth, and re-run the v1 baseline, in a change of its own before this one. This change's baseline is that re-run, not `20260922-155901-path_a-148bac7`.

## What Changes

- Add a business validation module (`V1`–`V7`, including V2b and the WSFE form of V3) that takes a parsed `Invoice` and returns typed problems, never raises for a business problem, and imports nothing from the model client or the prompts.
- Add a document-processing pipeline between extraction and callers: extract → validate → corrective retry with the previous extraction and its problems in context → final outcome. Hard cap on attempts per document (default 3). After the last attempt the outcome is an explicit validation failure carrying the remaining problems, never the last invalid object. Client-side schema failures (`invalid_output`) enter the same corrective path.
- Widen the model client to accept a multi-turn conversation (needed to resend the previous extraction and the problems) and to report how many transport requests each call took, so transport retries and corrective attempts are counted separately.
- Add a versioned corrective prompt (`prompts/correct_invoice/v1.md`).
- Widen the evaluation: run records keep every attempt and its validation problems, attempt count and cost/latency summed over attempts; the report adds per-check validation failure counts, the attempt distribution, the retry rate with the 30% heuristic flag, and cost per document including every attempt. Old run records stay readable.
- Add `--model`, `--max-attempts` and `--no-validation` to the evaluation command, so each version changes exactly one lever.
- Add the iteration protocol: a version registry with the hypothesis written before the run, a paired version-vs-version comparison (McNemar on documents, per-field deltas, explicit noise statement), and an iteration log table rendered from committed run records into the README.
- Run the iterations: v2 validation + corrective retries, v3 prompt v2 (null vs zero for an absent IVA column, from the failure analysis), v4 Haiku 4.5, v5 Opus 5.
- Record a finding from planning: failure-analysis hypothesis 2 ("a B/C invoice has no non-null `vat_rate`") is contradicted by the dataset (B03 and B06 legitimately print an IVA column), so it is not implemented as a check. B05's invented `"0"` is a prompt problem, not a validation one.

## Capabilities

### New Capabilities
- `invoice-validation`: the deterministic business validator, its checks V1–V7, the tolerance rule and its independence from the model (PRD 04 R1).
- `corrective-retries`: the per-document pipeline from extraction to final outcome, the corrective conversation, the attempt cap and the explicit validation failure (PRD 04 R2).
- `iteration-protocol`: one lever per version, hypothesis before the run, paired version comparison, the iteration log and the stopping rule (PRD 04 R3, R4, R5.1).

### Modified Capabilities
- `model-client`: accepts a multi-turn conversation, not only one user turn; each call record reports its transport request count.
- `invoice-evaluation`: run records hold every attempt with its validation result; validation failure counts as `explicit_failure`; the report adds per-check validation counts, retry rate and cost over all attempts; execution enforces the per-document attempt cap.

## Impact

- New code: `src/invoice_extractor/validation.py`, `src/invoice_extractor/processing.py` (pipeline), `src/invoice_extractor/evaluation/version_comparison.py`, `src/invoice_extractor/iterations.py` (log rendering), all API-free tested.
- Changed code: `client.py` (conversation input, transport count), `evaluation/execute.py`, `evaluation/run_record.py` (record format v2 with a reader for v1 records), `evaluation/report.py`, `evaluate.py` (flags), `extract_one.py` (goes through the pipeline).
- New prompts: `prompts/correct_invoice/v1.md`, `prompts/extract_invoice/v2.md`.
- New docs: `docs/iterations/` (one hypothesis file per version), iteration log section in `README.md`.
- Spend: about USD 6–8 of the USD 10 iteration budget (design has the estimate per run). No new dependencies.
- Known conflict, not fixed here: the real set's "IVA Contenido" tickets will fail V3/V5 (PRD 04 R6 first lever). Reported in the real-set section only.
