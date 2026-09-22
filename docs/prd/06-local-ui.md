# PRD 06 · Local UI

Status: draft · Stage 6 of 6 · Depends on: PRD 04 (validation + retries), PRD 05 (CLI `process`/`batch`, review queue) · Course estimate: ~3 h

## Why

The CLI proves the system works to an engineer. A person from the accounting team, or someone evaluating the portfolio, understands it faster by dropping a few invoices on a page and seeing each one classified, its data validated, and its cost and failures shown next to it. This stage adds a thin local UI on top of the same pipeline the CLI uses. It adds no new extraction logic. The UI is a view of the same outcomes, costs and problems the measurement stages already produce, never a way to hide them.

## Scope

**In**
- A local, single-user web UI started with one command.
- Upload one or more documents (PDF, JPG, PNG) and process them through the PRD 05 `process` path.
- A results table that classifies every document by outcome and invoice type.
- A detail view per document: the validated invoice, or the explicit failure with its problems, next to the source document.
- Export of the session's results (JSONL identical to `batch`, and CSV for spreadsheets).
- Optional: working the PRD 05 R6 human review queue from the UI.

**Out**
- Deployment, authentication, multi-user use, persistence across sessions beyond explicit export files.
- Any extraction, validation or retry logic inside the UI module (see R1).
- Editing ground truth or the evaluation dataset from the UI.
- Running `evaluate` from the UI. Reports stay a CLI concern.
- Integration with accounting systems or ARCA/AFIP.

## Requirements

### R1 · Thin layer

- **R1.1** The UI calls the same public function the `process` command calls (PRD 05 R1.1) and receives the same typed result. It never builds prompts, calls the model client or runs validation itself (CC-2).
- **R1.2** The UI lives in its own module (`src/invoice_extractor/ui/` or equivalent), and its framework dependency is an optional extra (`pip install -e .[ui]`). The core package and `pytest` do not require it.
- **R1.3** Removing the UI module leaves the CLI and the test suite unchanged.

### R2 · Upload and processing

- **R2.1** Accepts PDF, JPG and PNG, one or many files per upload. Any other format is rejected in the UI with the same message the CLI gives (PRD 05 R1.5), before any model call.
- **R2.2** Files are processed sequentially, or with a small fixed concurrency, and show per-document progress.
- **R2.3** The per-run spend cap and the per-document attempt cap (CC-5) apply to a UI session exactly as to a `batch` run. When the cap is reached, the remaining documents are shown as "not processed: spend cap reached", never silently dropped.
- **R2.4** A missing API key shows the same actionable message as the CLI (PRD 05 R1.6), with no stack trace.
- **R2.5** Uploaded files stay local: they are held in a temp directory that the UI deletes at the end of the session, and are never written into the repo (CC-7).

### R3 · Classification view

One row per document, with:

| Column | Source |
|---|---|
| File name | upload |
| Outcome | `extracted` · `failed` (with reason: `not_an_invoice`, `unsupported_document_type`, `illegible`, `missing_mandatory_data`, validation failure after cap) · `error` (transport/API) |
| Invoice type | `invoice_type` (A, B, C, E), blank on failures |
| Issuer, issue date, total, currency | extracted invoice |
| Attempts | transport and corrective, both counts (PRD 04 R2.4) |
| Cost (USD), latency | the extraction record |

- **R3.1** Filters by outcome and by invoice type, and a summary line: documents per outcome, per type, total cost, mean and max latency.
- **R3.2** A failure is visually distinct from a success. It is never shown as a partially filled invoice.

### R4 · Detail view

- **R4.1** Source document preview (PDF first page or the image) next to the extracted fields.
- **R4.2** For an extracted invoice: every schema field, the items table, and the list of validation checks that ran with their result.
- **R4.3** For a failure: the reason, the remaining validation problems, and the last extraction marked as rejected, matching the PRD 05 R6 review record.
- **R4.4** Raw JSON of the result, copyable.

### R5 · Export

- **R5.1** "Download JSONL" produces the same line format as `batch` (PRD 05 R1.2), including the closing summary line.
- **R5.2** "Download CSV" flattens one row per invoice (header fields and totals) and a second CSV for items, keyed by file name.
- **R5.3** No automatic writes outside the temp directory. Files leave the session only through an explicit download.

### R6 · Optional: review queue

- **R6.1** A tab lists documents that ended in an explicit failure, with their problems, as PRD 05 R6 defines them.
- **R6.2** A human can mark a document "accepted as corrected" with edited fields, or "rejected". The corrected invoice is validated by the same validator before it can be accepted.
- **R6.3** Corrections are exported to a `review.jsonl`. They never feed back into `ground_truth/` or any headline metric.

### R7 · Tests

- **R7.1** The UI's own logic (result → table row, filters, summary, CSV flattening, spend-cap state) is plain functions, unit-tested with fixture results and no API (CC-8).
- **R7.2** One smoke test starts the app with a fake client and processes a fixture document, if the chosen framework offers a test harness. Otherwise a manual check is recorded in the README.

### R8 · README

- **R8.1** A "Run the UI" section: install the extra, the one start command, a screenshot.
- **R8.2** The demo section (PRD 05 R4.2) can use a GIF of the UI instead of terminal lines.

## Acceptance criteria

- [ ] `invoice-extractor ui` (or the documented equivalent) opens the UI locally after `pip install -e .[ui]`.
- [ ] Uploading a mix of valid invoices and a `not_an_invoice` negative shows each one classified correctly, with the negative as an explicit failure.
- [ ] The spend cap stops a session and the remaining documents are listed as not processed.
- [ ] The JSONL export matches `batch` output for the same files (same fields, same outcomes).
- [ ] The UI module contains no model calls, prompt text or validation rules (checked by review and by R1.3).
- [ ] `pytest` passes with no API key and without the UI extra installed.

## Risks

| Risk | Mitigation |
|---|---|
| Business logic leaks into the UI and diverges from the CLI | R1 thin layer; UI calls one function; R1.3 removal check |
| UI makes spending easy (drag 200 files) | Spend cap and attempt cap enforced per session (R2.3); estimated cost shown before processing large uploads |
| A polished UI implies production readiness | Known limitations from PRD 05 R4.7 repeated on the UI's landing text |
| Personal data from real invoices uploaded by the user ends up in the repo | Temp directory outside the repo, deleted at session end (R2.5); `.gitignore` covers any default export path |
| Framework choice adds heavy dependencies to the core | Optional extra (R1.2) |

## Open questions

- **OQ-6.1** Framework: Streamlit (fastest to build, file upload and tables built in, heavier dependency) or Gradio (lighter, good for demos)? Leaning Streamlit.
- **OQ-6.2** Concurrency: sequential (simplest, clear progress) or a small async pool reusing the `batch` implementation?
- **OQ-6.3** Should the cost estimate before processing use a fixed per-page estimate or the mean cost/doc of the latest run record?
- **OQ-6.4** Is R6 (review queue) in this stage, or left for later if PRD 05 R6 was not built?
