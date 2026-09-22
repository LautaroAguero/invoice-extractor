## MODIFIED Requirements

### Requirement: Run record persistence

Every evaluation run SHALL write a run record to `runs/` containing: the config (model ID, extraction prompt version, corrective prompt version, whether validation was on, attempt cap, schema hash of the schema actually sent after `anthropic.transform_schema`, `anthropic` and `pydantic` versions, ingestion path, generator version, git SHA, timestamp), one entry per document (final outcome, every attempt with its call record and validation problems, corrective attempt count, transport request count per call, tokens including cache and thinking-in-output, cost and latency summed over attempts), and aggregates. Run records written before this format SHALL remain readable, and SHALL be read as runs with validation off and one attempt per document.

#### Scenario: Run record fields
- **WHEN** an evaluation run over the synthetic dataset completes
- **THEN** the run record contains the config block, one per-document entry for every document in the manifest, and aggregate counts

#### Scenario: Every attempt kept
- **WHEN** a document succeeds on its second attempt
- **THEN** its entry holds both attempts, the first with its validation problems, and its cost is the sum of both calls

#### Scenario: Stage 3 run record still readable
- **WHEN** the stage 3 baseline run record is read
- **THEN** it loads without error, reports validation off and 1 attempt per document, and renders the same report as before

### Requirement: Document-level outcome classification

Each document's actual outcome SHALL be classified as `extracted` or `explicit_failure`, and cross-referenced against its manifest `expected_outcome` to produce one of: extraction, false rejection, false acceptance, or correct rejection. A validation failure after the last attempt SHALL be an `explicit_failure`. Field precision SHALL be computed only on the final accepted invoice.

#### Scenario: False acceptance
- **WHEN** a document with `expected_outcome` `explicit_failure` is extracted as a valid invoice
- **THEN** it is classified as a false acceptance

#### Scenario: Validation failure is a rejection
- **WHEN** an in-domain document ends in a validation failure after the attempt cap
- **THEN** it is classified as a false rejection and adds nothing to field precision

### Requirement: Quality report

One command SHALL produce, from a run record, a report containing: the correct-outcome rate and its components (extraction rate, false rejections, correct rejections with reason agreement, false acceptances), invented and missed value counts, per-field precision over successful extractions (including list `_exact` and `_per_entry` metrics with extra-entry counts), a per-tag breakdown, attempts distribution, and cost and latency summaries. When validation was on, it SHALL also contain: for each check, how many attempts passed the schema but failed that check; how many documents needed a corrective attempt, as a rate with n and interval, flagged when it is 30% or more; how many documents ended in a validation failure; and transport retries counted apart from corrective attempts. Cost per document and latency SHALL include every attempt. Every rate SHALL be shown with its n and a 95% Wilson confidence interval, and the worst-performing field SHALL be marked automatically.

#### Scenario: Report shows n and interval
- **WHEN** the report is rendered
- **THEN** every percentage line is accompanied by its n and a 95% Wilson interval

#### Scenario: Worst field marked
- **WHEN** the report is rendered
- **THEN** the field with the lowest precision among scored fields is marked as the worst field

#### Scenario: Validation counts per check
- **WHEN** the report is rendered from a run where two first attempts failed `V3` and one failed `V1`
- **THEN** the validation section shows `V3` 2 and `V1` 1, and the documents that needed a corrective attempt

#### Scenario: High retry rate flagged
- **WHEN** 10 of 30 documents needed a corrective attempt
- **THEN** the report flags the retry rate as a prompt or schema problem

### Requirement: Bounded, capped execution

An evaluation run SHALL run documents with bounded concurrency, SHALL cap corrective attempts per document, and SHALL stop when a configured per-run spend cap is reached, saving the partial run record marked incomplete. A document SHALL NOT start while the cost of completed documents has reached the cap. A failure on one document SHALL be recorded as that document's outcome and SHALL NOT abort the run. An incomplete run record SHALL NOT be reported as a full run.

#### Scenario: Spend cap stops a run
- **WHEN** the cumulative cost of a run reaches its configured spend cap partway through the dataset
- **THEN** the run stops, the partial run record is marked incomplete, and report generation rejects it as a full result

#### Scenario: One document's failure does not abort the run
- **WHEN** one document's extraction ends in an API error
- **THEN** the run continues to the remaining documents and the record's outcome for that document is the failure

#### Scenario: Attempt cap applies in a run
- **WHEN** a run uses an attempt cap of 2 and a document never passes validation
- **THEN** that document makes exactly 2 attempts and ends in a validation failure

## ADDED Requirements

### Requirement: One lever selectable per run

The evaluation command SHALL let a run select the model (from the configured price table), the extraction prompt version, the attempt cap and whether validation is on, and SHALL record each choice in the run config. A model with no price entry SHALL fail before any request is sent.

#### Scenario: Model override
- **WHEN** a run is started with model `claude-haiku-4-5`
- **THEN** every request uses that model and the run config records it

#### Scenario: Run ID distinguishes the lever
- **WHEN** two runs with different models or prompt versions start in the same second on the same commit
- **THEN** they get different run IDs
