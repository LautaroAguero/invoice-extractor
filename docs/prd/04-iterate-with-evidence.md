# PRD 04 · Iterate with evidence

Status: draft · Stage 4 of 5 · Depends on: PRD 03 (baseline run record + failure analysis) · Course estimate: ~3 h

## Why

Structured outputs guarantee **shape**, not **truth**: a perfectly typed invoice can carry a total that is not the invoice's total. This stage adds the detector for that (business validation) and the recovery path (corrective retries). It then improves the extractor one measured change at a time. The iteration log with numbers is the portfolio artifact: it shows measurement, iteration, and an understanding of the trade-off between quality and cost.

## Scope

**In**
- Business validation, a separate module that knows nothing about the model.
- Corrective retries, with the previous errors in context and a hard attempt cap.
- An iteration protocol and the iteration log in the README.
- Changes to the schema, prompt, ingestion and model parameters, each driven by the PRD 03 failure analysis.
- Optional: small vs large model comparison, Batch API cost comparison, measured prompt caching.

**Out**
- CLI polish, README beyond the log, and tests of the final CLI (PRD 05).
- Changes that are not measured. A change without a run record is not an iteration.

## Requirements

### R1 · Business validation (≥5 checks the schema cannot express)

The validator takes a parsed invoice and returns a list of typed problems; it never raises for a business problem. Field names refer to the stage 1 schema (`src/invoice_extractor/schema.py`). V2b and the WSFE form of V3 were added on 2026-09-14 by the stage 1 design (D2, D3). Checks:

| # | Check | Redundancy it exploits |
|---|---|---|
| V1 | Issuer CUIT (and customer CUIT when present) passes the mod-11 check digit | Identifier self-check |
| V2 | Sum of item amounts equals net amount (within explicit rounding rules) | Items ↔ net |
| V2b | Per item: quantity × unit price − discount equals line amount (within rounding) | Line arithmetic ↔ printed amount |
| V3 | WSFE total: net + non-taxed + exempt + VAT + sum(other taxes) equals total; absent terms count as zero, and VAT is `vat_amount` or, when that is not printed, the sum of `vat_breakdown` | Totals |
| V4 | Each VAT breakdown amount equals base × rate (within rounding). The base per rate is not printed: it is the sum of line amounts of the items with that `vat_rate` | Rates ↔ amounts |
| V5 | Invoice type rules: A discriminates VAT and has a customer CUIT; B and C show no VAT breakdown; E uses a foreign currency with an exchange rate, or explains why not | Fiscal rules ↔ fields |
| V6 | Dates: issue date not in the future; due date ≥ issue date; CAE expiry ≥ issue date | Date coherence |
| V7 | Formats: point of sale 5 digits, invoice number 8 digits, CAE 14 digits | Identifier formats |

- **R1.1** The validator is deterministic and unit-tested without the API, including corrupted invoices that pass the schema but fail validation (course exercise 5.3).
- **R1.2** For every run, the report counts how many extractions passed the schema but failed validation, per check.

### R2 · Corrective retries

- **R2.1** When validation fails, the next attempt resends the conversation with the previous extraction and the list of problems, asking for a correction or an explicit failure if the document does not allow a consistent extraction.
- **R2.2** Hard cap on attempts per document (default 3, configurable, never unbounded). After the last attempt the result is an **explicit failure carrying the remaining problems**, never the last invalid object.
- **R2.3** Schema-level failures that the SDK validates client-side (constraints stripped from the API schema) enter the same corrective path.
- **R2.4** Transport retries (PRD 01 R2.5) are not counted as corrective attempts; the run record keeps both counts.
- **R2.5** Attempt distribution and cost per document **including all attempts** are reported. The course heuristic: if ~30% of documents need a retry, the problem is the prompt or schema, not the retries.

### R3 · Iteration protocol

- **R3.1 One change per version.** Each version changes one lever: schema descriptions, prompt, examples, ingestion path, effort, model, or validation/retry settings.
- **R3.2 Hypothesis first.** Before running, write the hypothesis and the failure-analysis evidence it comes from.
- **R3.3 Full dataset, paired.** Each version runs over the full dataset. Its comparison against the previous version is paired (McNemar per-document, per-field deltas), and it states whether the difference clears the noise floor.
- **R3.4 Record kept.** Each version keeps its run record in `runs/` and its prompt in `prompts/extract_invoice/vN.md`.
- **R3.5 Examples not from the eval set.** Few-shot examples come from seeds disjoint from `ground_truth/` (PRD 02 R6).
- **R3.6 Regressions logged.** A change that makes things worse gets logged too. A negative result is evidence.

### R4 · Iteration log (in README)

| Version | Change | Hypothesis | Correct outcome (95% CI) | Worst field | Invented values | Retries (docs) | Cost/doc | p95 | Paired vs prev |
|---|---|---|---|---|---|---|---|---|---|
| v1 | baseline | — | … | … | … | … | … | … | — |

Each number links to, or can be regenerated from, a committed run record.

### R5 · Optional comparisons (in order of value)

- **R5.1 Model comparison.** Run the same dataset with a large model (`claude-opus-5`) and a small one (`claude-haiku-4-5`). Tabulate precision, invented values and retries against cost/doc and p95. Include effort settings on Opus 5 if thinking cost is material.
- **R5.2 Batch API.** Run the dataset through the Message Batches API and compare measured cost and end-to-end time against the synchronous run.
- **R5.3 Prompt caching.** Only if the fixed prefix (system prompt + schema + examples) is above the model's minimum cacheable size. Report the measured `cache_read_input_tokens` and the saving; if the prefix is too small, document that caching does not apply and why.

## Acceptance criteria

- [ ] Validation implements ≥5 checks from R1, each with unit tests including a corrupted invoice.
- [ ] Retries have a hard cap; a document that cannot be fixed ends in an explicit failure with its problems (verified with a mocked client that always returns an invalid invoice).
- [ ] `not_an_invoice` documents end in explicit failures, not invented data.
- [ ] The README iteration log has ≥3 versions after the baseline, every row backed by a run record and a paired comparison.
- [ ] Cost per document includes every attempt and is measured.
- [ ] At least one row states honestly that its difference is within noise, if that is the case.

## Risks

| Risk | Mitigation |
|---|---|
| Overfitting the prompt to 30 known documents | R3.5; keep hypotheses tied to failure categories, not to specific documents |
| Retries mask a bad prompt and multiply cost | R2.5 reporting; treat a high retry rate as a finding |
| Chasing gains inside the noise floor | R3.3 paired test and explicit noise statement |
| Validation too strict, so valid invoices get rejected (for example rounding on V2–V4) | Rounding rules explicit and unit-tested; false rejections are a report line |

## Open questions

- **OQ-4.1** Rounding tolerance for V2–V4: per-line rounding means sums can differ by cents. Fixed ±0.01 × lines, or percentage?
- **OQ-4.2** When V5 fails only because the customer CUIT is legitimately absent on an A invoice, is that an extraction error or a document error? The answer determines whether it retries or goes to human review.
- **OQ-4.3** Stopping condition: a target precision, a number of iterations, or a budget?
