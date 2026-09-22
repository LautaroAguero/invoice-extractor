## Purpose

Makes every improvement to the extractor a measured, paired, logged experiment: one lever per version, a hypothesis written before the run, a comparison against the previous version that states whether it clears the noise floor, and an iteration log whose numbers come from committed run records.

## ADDED Requirements

### Requirement: One lever per version

Each version SHALL change exactly one lever relative to the version it is compared against: schema descriptions, extraction prompt, examples, ingestion path, model, effort, or validation/retry settings. The version's registry entry SHALL name that lever and the version it is compared against.

#### Scenario: Registry names the lever
- **WHEN** a version is registered
- **THEN** its entry names exactly one lever and its comparison version

### Requirement: Hypothesis before the run

Each version SHALL have a hypothesis file, committed before its run record, that states the hypothesis, the failure-analysis evidence it comes from, and the expected effect.

#### Scenario: Hypothesis precedes the run
- **WHEN** a version's run record is committed
- **THEN** its hypothesis file exists in an earlier or the same commit, and the run record's timestamp is later than the hypothesis file's commit

### Requirement: Full dataset, paired comparison

Each version SHALL run over the full synthetic dataset. Its comparison against its comparison version SHALL be paired on the same documents: an exact McNemar test on per-document correct outcome, per-field precision deltas, invented-value deltas, and cost per document and p95 latency for both. The comparison SHALL state whether the difference clears the noise floor (p < 0.05) or is within noise.

#### Scenario: Within noise
- **WHEN** two versions differ on 1 document out of 30
- **THEN** the comparison reports the McNemar p-value and states the difference is within noise

#### Scenario: Different manifests are not compared
- **WHEN** the two run records were scored on different manifests or under different measurement rules
- **THEN** the comparison refuses to run and names the mismatch

### Requirement: Iteration log from run records

The README SHALL contain an iteration log with one row per version: version, change, hypothesis, correct outcome with 95% interval, worst field, invented values, documents with a retry, cost per document, p95 latency, and the paired result against its comparison version. Every number SHALL be regenerable from a committed run record without calling the model. Regressions SHALL be logged like improvements.

#### Scenario: Log regenerated offline
- **WHEN** the iteration log is rendered with no API key
- **THEN** every row's numbers are recomputed from the committed run records and match the README

#### Scenario: Regression logged
- **WHEN** a version performs worse than its comparison version
- **THEN** its row appears in the log with the worse numbers

### Requirement: Examples never come from the evaluation set

Any example added to a prompt SHALL come from a document or seed disjoint from `ground_truth/`, or be a textual rule that quotes no evaluation document.

#### Scenario: Example provenance
- **WHEN** a prompt version adds an example
- **THEN** its hypothesis file names the example's source and that source is not in the manifest

### Requirement: Stopping rule and budget

Iteration SHALL stop when at least 3 versions after the baseline are logged and the model comparison (Haiku 4.5 and Opus 5 against Sonnet 5) is done, or when the iteration budget of USD 10 is spent. Every run SHALL have its own spend cap, and the sum of recorded run costs SHALL be reported next to the log.

#### Scenario: Budget reached
- **WHEN** the recorded cost of this stage's runs reaches USD 10
- **THEN** no further version is run, and the log states that the budget stopped the iteration

### Requirement: Model comparison table

The iteration record SHALL include a table comparing Sonnet 5, Haiku 4.5 and Opus 5 on the same prompt and settings: correct outcome, field precision, invented values, documents with a retry, cost per document and p95 latency.

#### Scenario: Three models tabulated
- **WHEN** the model comparison runs are complete
- **THEN** the table has one row per model, each backed by a run record
