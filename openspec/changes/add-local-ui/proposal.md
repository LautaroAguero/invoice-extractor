## Why

The extractor can only be driven from a terminal today. The user's goal for this project is to drop an invoice on a page and see it classified with its cost: "pasarle una factura por el cliente web que la clasifique y que me dé cuánto costó y los demás datos" (2026-09-22). This change implements the first slice of PRD 06 · Local UI: upload, classify, show every extracted field, and show the measured cost, tokens and latency.

PRD 06 requirements covered: R1 (thin layer, optional extra), R2 (upload, formats, spend cap, missing key, temp files), R3 (classification view), R4.1/R4.2/R4.4 (detail view), R7 (API-free tests), R8.1 (README section). Deliberately out of this slice: R5 (JSONL/CSV export), R6 (review queue), and the validation-check list of R4.2, which needs `add-validation-and-iterations`.

Ordering note: PRD 06 is stage 6 and this change lands before stages 4 and 5. It is a view, not an accuracy change — no measurement, prompt, schema or scoring rule moves — so "nothing gets improved before stage 3 can measure it" still holds. The UI reads what the pipeline already produces.

## What Changes

- Add a local, single-user Streamlit page: upload one or more documents, process them one at a time, and see a result row per document plus a detail view.
- Classification per document: invoice type (A, B, C, E) or an explicit failure with its reason, visually distinct from a success.
- Measured numbers per document, straight from the call record: cost in USD, input/output tokens, latency, stop reason and attempts.
- Detail view: every extracted field, the items table, the VAT breakdown, and the raw JSON.
- A per-session spend cap (default USD 1.00) that stops processing and says so, and an actionable message when the API key is missing.
- Accept PNG input, which the extractor rejects today (PDF and JPG only). Screenshots of invoices are the common case for a person using a page like this.
- Ship the UI as an optional extra (`pip install -e .[ui]`), so the core package and `pytest` never need Streamlit.

## Capabilities

### New Capabilities
- `local-ui`: the local page — upload, classification, per-document measured numbers, detail view, session spend cap, and its independence from extraction logic (PRD 06 R1–R4).

### Modified Capabilities
- `invoice-extraction`: single-document extraction accepts PNG as an image block, alongside PDF and JPG.

## Impact

- New code: `src/invoice_extractor/ui/` — `view.py` (pure, Streamlit-free, tested), `service.py` (the one call into the pipeline), `app.py` (the page), `__main__.py` (launcher).
- Changed code: `extraction.py` (PNG image block) and its tests.
- New optional dependency group `ui = ["streamlit>=1.40,<2"]` in `pyproject.toml`.
- New README section: how to run the UI.
- Spend: only what the user uploads. About USD 0.04 per invoice on Sonnet 5, USD 0.01 on Haiku 4.5, capped per session.
- When `add-validation-and-iterations` lands, `service.py` switches from `extract_document` to `process_document` in one place and the UI gains validation and retries without further change.
