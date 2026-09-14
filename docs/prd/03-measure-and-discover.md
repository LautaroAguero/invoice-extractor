# PRD 03 · Measure and discover

Status: draft · Stage 3 of 5 · Depends on: PRD 01, PRD 02, OQ-1 · Course estimate: ~2 h

## Why

This stage turns "it seems to work" into numbers. Running the baseline over the full dataset will show that one specific field fails much more than the rest; **that discovery is the heart of the project** and the input to every iteration in PRD 04. The stage also settles, with evidence, which ingestion path wins for this domain.

## Scope

**In**
- An evaluation harness that runs the extractor over the dataset and compares against ground truth.
- The quality report, generated with one command.
- Persisted run records, so reports can be regenerated without calling the API.
- A paired comparison of the two PDF ingestion paths.
- A written failure analysis of the baseline.

**Out**
- Fixing what the analysis finds (PRD 04).
- Business validation and corrective retries (PRD 04). In this stage every document has exactly 1 attempt.
- The final CLI polish (PRD 05). A minimal entry point is enough here.

## Requirements

### R1 · Run record

- **R1.1** Every evaluation run writes a record to `runs/` containing:
  - config: model ID, prompt version, schema hash, ingestion path, generator version, git SHA, timestamp;
  - per document: prediction or typed failure, attempts, tokens (including cache and thinking-in-output), cost, latency;
  - aggregates.
- **R1.2** The report is a pure function of a run record: `evaluate` and `report` are separable, and re-rendering a report never calls the model.
- **R1.3** Run records contain only synthetic data and are safe to commit. Committing the ones behind the README numbers is what makes those numbers verifiable.

### R2 · Comparison

- **R2.1** Values are normalized before comparing: decimals compared exactly after parsing; dates as ISO; strings case- and whitespace-normalized; CUIT digits only. Normalization is unit-tested.
- **R2.2** Comparison follows the rules decided in OQ-1 (below). Those rules are written in `docs/measurement-rules.md` **before** the first baseline run, so the numbers cannot be bent to fit.
- **R2.3** A value predicted where ground truth is absent is counted separately as an **invented value**. It is the most dangerous error an extractor makes and gets its own line in the report.

### R3 · Report

One command produces it, in the terminal and as markdown. It contains at least:

```
DOCUMENTS            30
Correct outcome      n/30  (xx.x%)  [95% CI]
  extracted          n
  explicit failure   n   (correct rejections n · false rejections n)
Invented values      n

FIELD PRECISION                n/N    %      95% CI
  <field>                      ...
  items (per OQ-1 rule)        ...
  <worst field>                ...           ← worst field

BY TAG                         (multi_page, foreign_currency, skewed_scan, ...)
ATTEMPTS             1: n · 2: n · 3: n
COST                 total $x.xxxx · mean $x.xxxx/doc   (measured from usage)
LATENCY              p50 x.xs · p95 x.xs                (wall clock per document)
```

- **R3.1** Every rate shows its n and a Wilson interval. No bare percentages.
- **R3.2** The worst field is marked automatically.
- **R3.3** A per-tag breakdown shows whether failures concentrate in the hard cases.

### R4 · Execution

- **R4.1** Documents run with bounded concurrency and respect rate limits (backoff comes from the client, PRD 01 R2.5).
- **R4.2** Each run has a spend cap. When the cap is reached the run stops, the partial record is saved and marked incomplete, and nothing is reported as a full run.
- **R4.3** A failure on one document (API error, refusal, truncation) is recorded as that document's outcome and does not abort the run.

### R5 · Ingestion path comparison (course requirement 2)

- **R5.1** Path A: PDF sent as a document block. Path B: text extracted locally from the PDF and sent as text.
- **R5.2** Both paths run over the same documents; the comparison is paired (McNemar on per-document outcome, and per-field deltas).
- **R5.3** For documents with no text layer, path B must end in an explicit failure, never in an extraction from empty text.
- **R5.4** The result table reports precision, invented values, cost/doc and p95 latency per path, and names the winner for this domain with its trade-off.

### R6 · Failure analysis

`docs/failure-analysis.md` classifies every wrong field of the baseline run into a category (misread value, column confusion, wrong field chosen, invented, formatting, rejection error) with counts and one example each. It ends with a ranked list of hypotheses for PRD 04, each pointing at the evidence.

## Acceptance criteria

- [ ] `docs/measurement-rules.md` exists and is committed before the baseline run record.
- [ ] One command produces the report from the dataset. A second command re-renders it from a saved run record without network access.
- [ ] Per-field precision and cost per document come from the run record, not estimates.
- [ ] The report shows n and a 95% interval for every rate, plus the invented-values count.
- [ ] A spend cap stops a run and the partial run is marked incomplete (verified with a mocked client).
- [ ] A paired comparison of path A vs path B exists with numbers and a stated winner.
- [ ] `docs/failure-analysis.md` names the worst field and ranks hypotheses with evidence.

## Risks

| Risk | Mitigation |
|---|---|
| Measurement rules chosen after seeing numbers | R2.2 ordering, enforced by commit history |
| Differences inside the noise floor get read as wins | R3.1 intervals, R5.2 paired test |
| Baseline near 100% leaves nothing to discover | Per-tag breakdown; if confirmed, strengthen the hard cases in PRD 02 before PRD 04 |
| Eval runs get expensive while iterating | Spend cap per run; re-render reports from records; cheaper model runs only as an explicit comparison |

## Open questions

- **OQ-1 (blocking) Measurement rules.** Decide and write them down before the first baseline:
  1. **Correct rejection:** does an explicit failure on a `not_an_invoice` document count as a correct outcome in the headline rate, or is it reported only on a separate line?
  2. **Optional field absent:** ground truth `null` and prediction `null`: correct, or excluded from the denominator?
  3. **Items:** whole list exact, per-item match (by position or by description), or both?
  4. **Field denominator:** all in-domain documents (a failed extraction counts as wrong for every field) or only successfully extracted documents? The course example uses the second (`cuit_emisor 24/28`); it hides failures inside field precision unless reported alongside.
  5. **Tolerance:** exact decimal match, or a tolerance for amounts?
- **OQ-3.1** Which local library for path B (pypdf, pdfplumber, pymupdf)? Table extraction quality differs, and so does licensing (pymupdf is AGPL).
