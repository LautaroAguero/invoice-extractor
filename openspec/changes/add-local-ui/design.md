## Context

See proposal.md for motivation. What the UI can build on today:

- `extract_document(path, *, client, prompt, max_tokens)` returns an `ExtractionRecord`: the source name, the prompt version and a `CallRecord` with the parsed `ExtractionResult` (or a typed `CallFailure`), tokens, stop reason, latency and cost from usage.
- `extract_one.py` already does the CLI version of exactly this flow, including the missing-key message and the config load.
- `document_content_block` accepts PDF and JPG and validates extension and magic bytes before any call.
- `add-validation-and-iterations` will introduce `process_document`, which wraps extraction with validation and corrective retries and returns a `ProcessedDocument`.

## Goals / Non-Goals

**Goals:**
- A page a person can use without knowing the repo: drop a file, read the result, see the cost.
- One place to change when the pipeline gains validation and retries.
- UI logic testable without Streamlit and without an API key.

**Non-Goals:**
- Export (PRD 06 R5) and the review queue (R6).
- The validation-check list in the detail view — it needs stage 4.
- Any deployment, auth or multi-user concern. It binds to localhost, as Streamlit does by default.

## Decisions

### D1. Streamlit, as an optional extra (OQ-6.1 resolved)

Streamlit (1.64 installed locally). It gives file upload, tables, layout and a dev loop with no front-end code, which is the whole point of a 2-3 hour slice. Gradio was the alternative; it is lighter, but its table and layout story is weaker for a document-plus-fields view. Declared in `pyproject.toml` as `[project.optional-dependencies] ui`, so `pytest` and the core install never pull it in.

### D2. Module layout: one call site, one pure module

```
src/invoice_extractor/ui/
  view.py      # pure: ResultRow, formatting, session totals, cap decision. No streamlit, no anthropic.
  service.py   # the only call into the pipeline: analyze_document(path, client, prompt) -> ExtractionRecord
  app.py       # the Streamlit page: widgets, state, rendering. Imports view + service.
  __main__.py  # `python -m invoice_extractor.ui` -> launches `streamlit run app.py`
```

When stage 4 lands, `service.py` switches to `process_document` and `view.py` gains the validation rows; `app.py` does not change shape. This is the "one place to change" the goals ask for (stage 4 task 3.5 will do it).

`view.py` holds everything worth testing: `row_from_record(record) -> ResultRow` (outcome kind, invoice type, reason, issuer, total, currency, cost, tokens, latency, attempts), the money/latency formatters, `session_totals(rows)`, and `cap_check(spent, cap, ...)`. Tests import it directly, with `CallRecord` fixtures built the way `tests/builders.py` already builds them.

### D3. Spend cap per session

`view.cap_check(spent_usd, cap_usd)` returns whether another document may start. The page keeps `spent_usd` in Streamlit session state and calls it before each document; when it refuses, the remaining uploads are listed as `not_processed` with the reason. Default cap USD 1.00, adjustable in the sidebar within `0 < cap <= 5`: the page cannot disable it, and the slider's own bounds are the ceiling (CC-5). The cap is per session, and it is checked before starting a document, so the overshoot is at most one document.

### D4. PNG input

`extraction.py` grows a media-type table: `.pdf` -> document block, `.jpg`/`.jpeg` -> `image/jpeg`, `.png` -> `image/png`. Magic bytes are checked per format (`%PDF-`, `\xff\xd8\xff`, `\x89PNG\r\n\x1a\n`), so a mislabelled file still fails before a call. This is the only change outside `ui/`.

### D5. Temp files and privacy

Each upload is written to a `tempfile.TemporaryDirectory()` created per document and removed in a `finally`, outside the repository (CC-7). Nothing is written into the repo: no run records, no results. The page states that it processes files locally and that results are not saved anywhere.

### D6. Model call site and failure handling

One call site: `service.analyze_document` -> `extract_document` -> `ModelClient.call`. Nothing new is added to the failure handling that stage 1 established:

| Failure | What the page shows |
|---|---|
| API error, timeout, rate limit (after SDK retries) | A failure row with kind `api_error` and its detail; the session continues |
| Truncated (`max_tokens`) or refused | A failure row with that kind |
| Invalid output (client-side schema) | A failure row with kind `invalid_output` |
| Model failure outcome (`not_an_invoice`, ...) | An explicit-failure row with the reason and detail |
| Auth, permission, unknown model, exhausted balance | Raised by the client: the page shows the message once and stops processing (these block every later call) |
| Unsupported file | Rejected before any call, with the CLI's message |

**Estimated cost per document** (measured baseline, Sonnet 5, path A): $0.0376 mean, p95 latency 44s. Haiku 4.5 would be roughly $0.01. The page shows the real number per document, so the estimate only sets the default cap.

### D7. Model and prompt selection

The sidebar offers the models in the price table (`config/extractor.toml`) with the configured one as the default, and the prompt versions present in `prompts/extract_invoice/`. Both go into the same `ModelClient`/`Prompt` the CLI builds; an unpriced model cannot be selected, because the list comes from the price table.

## Risks / Trade-offs

- [A page makes it easy to spend on a big upload] → Per-session cap checked before each document (D3), the estimated cost of the queued files shown before processing, and the real total after.
- [Pipeline logic drifts into the page] → One call site (D2), `view.py` free of framework and SDK imports, and a test that asserts those imports are absent.
- [A polished page suggests production readiness] → The page carries a short "what this is" line: synthetic-data project, measured on 30 documents, no ARCA validation, not a product.
- [Personal data in uploaded invoices] → Temp directory outside the repo, deleted after each document (D5); nothing is persisted.
- [Streamlit's rerun model recomputes state] → Results live in session state, keyed by upload; a rerun re-renders rows, it never re-processes a document.
