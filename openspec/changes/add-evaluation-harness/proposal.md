## Why

Stage 1 can extract one document and stage 2 has 30 documents with ground truth, but nothing yet runs the extractor over the dataset and turns the result into numbers. PRD 00 says the measurement is the product: without a report, the project cannot say which field is weakest or which ingestion path wins, and PRD 04's iterations have no evidence to point at. This change implements PRD 03 · Measure and discover in full: R1 (run record), R2 (comparison), R3 (report), R4 (execution: bounded concurrency and spend cap), R5 (ingestion path comparison, course requirement 2) and R6 (failure analysis).

Open questions this change depends on, both resolved:
- OQ-3.1 (library for path B) — resolved 2026-09-15: `pdfplumber`.
- OQ-3.2 (scoring of `vat_breakdown` and `other_taxes`) — resolved 2026-09-15: by position, same rule as `items`.

`docs/measurement-rules.md` (OQ-1) is already committed and fixes §1-§6 of the scoring rules this change implements; no scoring decision here reopens it.

## What Changes

- Add an evaluation harness that runs `extract_document` over every document in `ground_truth/manifest.jsonl` (and separately over `ground_truth_real/manifest.jsonl`) with bounded concurrency and a per-run spend cap, and persists a run record under `runs/` (JSON config/aggregates + one JSONL line per document).
- Add a comparison module that normalizes predictions and ground truth per `docs/measurement-rules.md` §4, matches list entries by position (§3), and classifies each document's outcome (§1) and each field (§2), including invented and missed values.
- Add a report generator that is a pure function of a run record (no network access) and renders the PRD 03 R3 report shape to the terminal and to markdown, with Wilson intervals on every rate and the real-set section (R3.5) kept out of every headline number.
- Widen ingestion to a second, local path: extract text with `pdfplumber` and send it instead of a document/image block. Add a paired comparison (McNemar exact + per-field deltas) between the document-block path (A) and the local-text path (B), including the required-failure behavior for `skewed_scan` and `image_input` documents on path B (R5.3).
- Add `docs/failure-analysis.md`, produced from the baseline run's comparison output, classifying every wrong field into a category with counts, one example each, and a ranked list of hypotheses for PRD 04.
- Widen `invoice-extraction` so JPG documents are sent as image blocks (needed for path A on `ground_truth/A09.jpg`, `B07.jpg` and both `ground_truth_real/` documents) instead of being rejected as unsupported input.
- Add `pdfplumber` as a normal dependency (MIT license, no isolation needed — unlike the GPL-3.0 generator).

## Capabilities

### New Capabilities
- `invoice-evaluation`: run records, ground-truth comparison and scoring, the quality report, bounded/capped execution, and the failure-analysis process (PRD 03 R1, R2, R3, R4, R6).
- `ingestion-path-comparison`: the local-text ingestion path and the paired A-vs-B comparison (PRD 03 R5, course requirement 2).

### Modified Capabilities
- `invoice-extraction`: accepts JPG input as an image block instead of rejecting every non-PDF file; the single-document entry point's supported-input scenario changes accordingly.

## Impact

- New code: `src/invoice_extractor/evaluation/` (or similar — run record, comparison, report, execution) and a local-text ingestion function, all covered by API-free tests (fake client, recorded/fixture documents).
- New CLI entry points: run the evaluation (writes a run record) and render a report from a saved run record.
- New dependency: `pdfplumber`.
- `src/invoice_extractor/extraction.py`: `pdf_document_block` gains an image-block counterpart and a non-PDF/non-JPG file still fails before any model call.
- New git-ignored output paths for anything derived from `ground_truth_real/` (run records, reports, failure examples), per PRD 03 R1.3.
- `docs/failure-analysis.md` (new) and `docs/measurement-rules.md` (read, not modified).
