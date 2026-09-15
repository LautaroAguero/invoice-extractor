# PRD 03 · Measure and discover

Status: draft · Stage 3 of 5 · Depends on: PRD 01, PRD 02, [measurement rules](../measurement-rules.md) · Course estimate: ~2 h

## Why

This stage turns "it seems to work" into numbers. Running the baseline over the full dataset will show that one specific field fails much more than the rest; **that discovery is the heart of the project** and the input to every iteration in PRD 04. The stage also settles, with evidence, which ingestion path wins for this domain.

## Scope

**In**
- An evaluation harness that runs the extractor over the dataset and compares against ground truth.
- The quality report, generated with one command.
- Persisted run records, so reports can be regenerated without calling the API.
- A paired comparison of the two PDF ingestion paths.
- A written failure analysis of the baseline.
- A separate report section for the 2-document real set, outside every headline number.

**Out**
- Fixing what the analysis finds (PRD 04).
- Business validation and corrective retries (PRD 04). In this stage every document has exactly 1 attempt.
- The final CLI polish (PRD 05). A minimal entry point is enough here.

## Requirements

### R1 · Run record

- **R1.1** Every evaluation run writes a record to `runs/` containing:
  - config: model ID, prompt version, schema hash (of the schema actually sent, after `anthropic.transform_schema`, not of the Pydantic source), `anthropic` and `pydantic` versions, ingestion path, generator version, git SHA, timestamp;
  - per document: prediction or typed failure, attempts, tokens (including cache and thinking-in-output), cost, latency;
  - aggregates.
- **R1.2** The report is a pure function of a run record: `evaluate` and `report` are separable, and re-rendering a report never calls the model.
- **R1.3** Run records over `ground_truth/` contain only synthetic data and are safe to commit. Committing the ones behind the README numbers is what makes those numbers verifiable. Run records, outputs and failure examples from `ground_truth_real/` contain third-party personal data (both issuers are natural persons, add-synthetic-dataset D10). They are written to a git-ignored location and never appear in committed reports, the failure analysis or the README.

### R2 · Comparison

- **R2.1** Values are normalized before comparing: decimals compared exactly after parsing; dates as ISO; strings case- and whitespace-normalized; CUIT digits only. Normalization is unit-tested.
- **R2.2** Comparison follows [docs/measurement-rules.md](../measurement-rules.md). The rules are committed **before** the first baseline run, so the numbers cannot be bent to fit, and they change only through that file's change log.
- **R2.3** A value predicted where ground truth is absent is counted separately as an **invented value**. It is the most dangerous error an extractor makes and gets its own line in the report.

### R3 · Report

One command produces it, in the terminal and as markdown. It contains at least:

```
DOCUMENTS            30   (in-domain n · negatives n)
Correct outcome      n/30  (xx.x%)  [95% CI]
  extraction rate    n/in-domain  (xx.x%)  [95% CI]
  false rejections   n
  correct rejections n
    reason agreement n/correct rejections (xx.x%)   ← informative, not scored
  false acceptances  n                        ← always shown
Invented values      n
Missed values        n

FIELD PRECISION  (over successful extractions: N)
                               n/N    %      95% CI
  <field>                      ...
  items_exact                  ...
  items_per_entry              n/entries ... (extra entries n)
  vat_breakdown_exact          ...
  vat_breakdown_per_entry      n/entries ... (extra entries n)
  other_taxes_exact            ...
  other_taxes_per_entry        n/entries ... (extra entries n)
  <worst field>                ...           ← worst field

BY TAG                         (multi_page, foreign_currency, skewed_scan, ...)
ATTEMPTS             1: n · 2: n · 3: n
COST                 total $x.xxxx · mean $x.xxxx/doc   (measured from usage)
LATENCY              p50 x.xs · p95 x.xs                (wall clock per document)
```

- **R3.1** Every rate shows its n and a Wilson interval. No bare percentages.
- **R3.2** The worst field is marked automatically.
- **R3.3** A per-tag breakdown shows whether failures concentrate in the hard cases.
- **R3.4 Reason agreement (negatives).** For each negative, `add-synthetic-dataset`'s manifest records an `expected_reason`. The report states how often the actual failure reason matches it, as its own line under "correct rejections" — informative only: a negative whose actual reason differs from `expected_reason` still counts as a correct rejection (PRD 02 spec: "Expected failure reason is informative, not scored").
- **R3.5 Real-set section.** Documents with manifest `source` `real` (`ground_truth_real/`, 2 documents, `add-synthetic-dataset`) never enter the `DOCUMENTS 30` count or any rate above. The report gives them their own section — same field-precision shape, run over 2 documents — clearly labeled as not a headline number and too small for a confidence interval.

### R4 · Execution

- **R4.1** Documents run with bounded concurrency and respect rate limits (backoff comes from the client, PRD 01 R2.5).
- **R4.2** Each run has a spend cap. When the cap is reached the run stops, the partial record is saved and marked incomplete, and nothing is reported as a full run.
- **R4.3** A failure on one document (API error, refusal, truncation) is recorded as that document's outcome and does not abort the run.

### R5 · Ingestion path comparison (course requirement 2)

- **R5.1** Path A: the PDF is sent as a document block, and JPG documents as image blocks. Path B: text is extracted locally with `pdfplumber` (`page.extract_text()`, default mode, all pages) and sent as text. There is no OCR: path B has no way to read an image.
- **R5.2** Both paths run over the same documents. The comparison is paired: McNemar on per-document outcome, and per-field deltas over the documents both paths extracted.
- **R5.3** For documents with no text layer (`skewed_scan`) and for JPG documents (`image_input`), path B must end in an explicit failure, never in an extraction from empty text. The report shows these documents as a separate group, because they measure coverage, not extraction quality.
- **R5.4** The result table reports precision, invented values, cost/doc and p95 latency per path, and names the winner for this domain with its trade-off.

### R6 · Failure analysis

`docs/failure-analysis.md` classifies every wrong field of the baseline run into a category (misread value, column confusion, wrong field chosen, invented, formatting, rejection error) with counts and one example each. It ends with a ranked list of hypotheses for PRD 04, each pointing at the evidence.

## Acceptance criteria

- [ ] `docs/measurement-rules.md` exists and is committed before the baseline run record.
- [ ] One command produces the report from the dataset. A second command re-renders it from a saved run record without network access.
- [ ] Per-field precision and cost per document come from the run record, not estimates.
- [ ] The report shows n and a 95% interval for every rate, the extraction rate next to field precision, and the invented, missed and extra-entry counts.
- [ ] A spend cap stops a run and the partial run is marked incomplete (verified with a mocked client).
- [ ] A paired comparison of path A vs path B exists with numbers and a stated winner.
- [ ] `docs/failure-analysis.md` names the worst field and ranks hypotheses with evidence.
- [ ] The report shows reason agreement for negatives, and a separate real-set section that no headline number includes.

## Risks

| Risk | Mitigation |
|---|---|
| Measurement rules chosen after seeing numbers | R2.2 ordering, enforced by commit history |
| Differences inside the noise floor get read as wins | R3.1 intervals, R5.2 paired test |
| Baseline near 100% leaves nothing to discover | Per-tag breakdown; if confirmed, strengthen the hard cases in PRD 02 before PRD 04 |
| Eval runs get expensive while iterating | Spend cap per run; re-render reports from records; cheaper model runs only as an explicit comparison |

## Open questions

- ~~OQ-1 Measurement rules~~ resolved 2026-09-14 (1a, 2a, 3c, 4b, 5a) in [docs/measurement-rules.md](../measurement-rules.md). Items are matched by position; reconsider only through the change log if the failure analysis shows shift cascades.
- ~~OQ-3.1 Library for path B~~ resolved 2026-09-15: **pdfplumber** (MIT, on pdfminer.six, MIT). Evidence: a comparison on the spike Factura A (one document, one layout, so it picks a default rather than proving a winner). Checked: item rows kept whole on one line, key values present, accents intact.

  | Library / mode | License | Rows intact | Key values | Chars |
  |---|---|---|---|---|
  | pypdf `extract_text()` | BSD-3 | 0/3 (columns emitted one after another) | 6/6 | 1,153 |
  | pypdf `extraction_mode="layout"` | BSD-3 | 3/3 | 6/6 | 2,722 |
  | **pdfplumber `extract_text()`** | MIT | **3/3** | 6/6 | **1,166** |
  | pdfplumber `layout=True` | MIT | 3/3 | 6/6 | 5,396 |
  | pypdfium2 `get_text_bounded()` | BSD-3/Apache-2.0 | 0/3 | 6/6 | 1,240 |
  | pymupdf `get_text(sort=True)` | **AGPL-3.0** | 3/3 | 6/6 | 2,385 |

  pdfplumber keeps rows together with the least text, which means fewer input tokens, and its license is compatible with any license for the extractor. It also offers `extract_tables()` if a later iteration needs it. pymupdf was the only one that split the overlapping "12.000,00 10,5%" cell cleanly, but AGPL rules it out. Every library except pymupdf merges that overlapping cell ("12.000,0010,5%3.780,00"), so it stays a real `dense_table` difficulty for path B. Switching library is a PRD 04 lever, and only through a measured run.
- ~~OQ-3.2 Scoring of `vat_breakdown` and `other_taxes`~~ resolved 2026-09-15: **by position, like items**, with the same exact and per-entry metrics. Recorded in the change log of [docs/measurement-rules.md](../measurement-rules.md) §3.
