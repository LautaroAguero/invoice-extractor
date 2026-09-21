## Purpose

Runs the extractor over the ground-truth dataset, scores every prediction against ground truth by `docs/measurement-rules.md`, and turns the result into a reproducible quality report and a failure analysis — the numbers that make "it works" verifiable.

## ADDED Requirements

### Requirement: Run record persistence

Every evaluation run SHALL write a run record to `runs/` containing: the config (model ID, prompt version, schema hash of the schema actually sent after `anthropic.transform_schema`, `anthropic` and `pydantic` versions, ingestion path, generator version, git SHA, timestamp), one entry per document (prediction or typed failure, attempts, tokens including cache and thinking-in-output, cost, latency), and aggregates.

#### Scenario: Run record fields
- **WHEN** an evaluation run over the synthetic dataset completes
- **THEN** the run record contains the config block, one per-document entry for every document in the manifest, and aggregate counts

### Requirement: Report is a pure function of a run record

Generating a report SHALL NOT call the model. Evaluating a dataset (producing a run record) and rendering a report from a run record SHALL be separate operations, and rendering SHALL be reproducible from the same run record.

#### Scenario: Re-render without network access
- **WHEN** a report is rendered from a saved run record with no API key configured
- **THEN** the report renders successfully and makes no model call

### Requirement: Real-set outputs are never committed

Run records, predictions and failure examples derived from `ground_truth_real/` SHALL be written only to a git-ignored location and SHALL NOT appear in any committed report or in `docs/failure-analysis.md`.

#### Scenario: Real-set run output location
- **WHEN** an evaluation run over `ground_truth_real/` completes
- **THEN** its run record is written under a git-ignored path, distinct from synthetic run records

### Requirement: Comparison follows the measurement rules

Predictions SHALL be compared to ground truth using the normalization and matching rules of `docs/measurement-rules.md`: exact decimal comparison for amounts, ISO dates, digits-only for CUIT, case- and whitespace-normalized strings, and list entries (`items`, `vat_breakdown`, `other_taxes`) matched by position.

#### Scenario: Amount comparison ignores formatting
- **WHEN** ground truth is `150000.00` and the prediction is `150000`
- **THEN** the field is scored correct

#### Scenario: Position-matched list entry
- **WHEN** a predicted `items` list is missing an early row that is present in ground truth
- **THEN** every following item is scored against the wrong ground-truth entry and counted as an error

### Requirement: Invented values are tracked separately

A predicted value where ground truth is `null` SHALL be counted as an invented value, distinct from a wrong value, and reported on its own line.

#### Scenario: Invented optional field
- **WHEN** ground truth for an optional field is `null` and the prediction is a non-null value
- **THEN** the field is scored wrong and also counted as an invented value

### Requirement: Document-level outcome classification

Each document's actual outcome SHALL be classified as `extracted` or `explicit_failure`, and cross-referenced against its manifest `expected_outcome` to produce one of: extraction, false rejection, false acceptance, or correct rejection.

#### Scenario: False acceptance
- **WHEN** a document with `expected_outcome` `explicit_failure` is extracted as a valid invoice
- **THEN** it is classified as a false acceptance

### Requirement: Quality report

One command SHALL produce, from a run record, a report containing: the correct-outcome rate and its components (extraction rate, false rejections, correct rejections with reason agreement, false acceptances), invented and missed value counts, per-field precision over successful extractions (including list `_exact` and `_per_entry` metrics with extra-entry counts), a per-tag breakdown, attempts distribution, and cost and latency summaries. Every rate SHALL be shown with its n and a 95% Wilson confidence interval, and the worst-performing field SHALL be marked automatically.

#### Scenario: Report shows n and interval
- **WHEN** the report is rendered
- **THEN** every percentage line is accompanied by its n and a 95% Wilson interval

#### Scenario: Worst field marked
- **WHEN** the report is rendered
- **THEN** the field with the lowest precision among scored fields is marked as the worst field

### Requirement: Reason agreement for negatives

For each correctly rejected negative document, the report SHALL state whether the model's actual failure reason matches the manifest's `expected_reason`, as an informative line that does not affect whether the document counts as a correct rejection.

#### Scenario: Reason mismatch still counts as correct rejection
- **WHEN** a negative document is correctly rejected but with a failure reason different from `expected_reason`
- **THEN** it still counts as a correct rejection, and the mismatch is shown only in the reason-agreement line

### Requirement: Real-set report section

Documents with manifest `source` `real` SHALL be excluded from the `DOCUMENTS` count and from every rate above it, and SHALL be reported in their own section with the same field-precision shape, labeled as not a headline number.

#### Scenario: Real document excluded from headline count
- **WHEN** the report is rendered over a run that included `ground_truth_real/` documents
- **THEN** those documents are absent from the `DOCUMENTS` count and appear only in the labeled real-set section

### Requirement: Bounded, capped execution

An evaluation run SHALL run documents with bounded concurrency and SHALL stop when a configured per-run spend cap is reached, saving the partial run record marked incomplete. A failure on one document SHALL be recorded as that document's outcome and SHALL NOT abort the run. An incomplete run record SHALL NOT be reported as a full run.

#### Scenario: Spend cap stops a run
- **WHEN** the cumulative cost of a run reaches its configured spend cap partway through the dataset
- **THEN** the run stops, the partial run record is marked incomplete, and report generation rejects it as a full result

#### Scenario: One document's failure does not abort the run
- **WHEN** one document's extraction ends in an API error
- **THEN** the run continues to the remaining documents and the record's outcome for that document is the failure

### Requirement: Failure analysis

`docs/failure-analysis.md` SHALL classify every wrong field of the baseline run's comparison into a category (misread value, column confusion, wrong field chosen, invented, formatting, rejection error, order-only mismatch for lists) with counts and one example each, and SHALL end with a ranked list of hypotheses for the next iteration, each pointing at supporting evidence.

#### Scenario: Failure analysis names the worst field
- **WHEN** `docs/failure-analysis.md` is generated from the baseline run
- **THEN** it names the worst-performing field and ranks at least one hypothesis with evidence
