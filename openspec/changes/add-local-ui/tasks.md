## 1. PNG input (spec invoice-extraction, MODIFIED; design D4)

- [x] 1.1 Replace the PDF/JPG dispatch in `extraction.py` with a media-type table covering `.pdf`, `.jpg`/`.jpeg` and `.png`, each checked against its magic bytes before any call; verify with fake-client tests: a PNG produces an `image/png` image block, a `.png` holding JPEG bytes is rejected, and `.txt` is still rejected with zero model calls

## 2. UI logic, framework-free (spec local-ui; design D2)

- [x] 2.1 Add `src/invoice_extractor/ui/view.py`: `ResultRow` (file name, outcome kind, invoice type, failure reason/detail, issuer, issue date, total, currency, cost, input/output tokens, latency, attempts), `row_from_record`, the money/latency formatters, `session_totals` and `cap_check`; verify with tests over fixture call records: an extracted Factura B row carries type `B` and its numbers, a model failure row carries the reason and no invoice fields, a call failure row carries the kind, totals of $0.04 + $0.03 give $0.07 over 2 documents, and `cap_check` refuses at and above the cap
- [x] 2.2 Add an import-boundary test asserting `ui/view.py` imports neither `streamlit` nor `anthropic` nor any prompt text, and that the whole suite passes without the UI extra installed

## 3. The page (design D2, D3, D5, D6, D7)

- [x] 3.1 Add `ui/service.py` with `analyze_document(path, *, client, prompt, max_tokens=None)` as the single call into the pipeline (today `extract_document`), plus `build_client(model)` reusing the CLI's config load and missing-key message; verify with a fake-client test that it returns the record and raises `ConfigError` with the actionable message when no key is set
- [x] 3.2 Add `ui/app.py`: uploader (PDF/JPG/PNG, several files), per-document processing with progress, result rows, session totals, sidebar with model, prompt version and spend cap, and the "what this is" note; temp file per document deleted in a `finally`
- [x] 3.3 Add the detail view per document: source preview next to the header fields, items table, VAT breakdown, totals, CAE, and the raw JSON; failures show reason and detail instead
- [x] 3.4 Add `ui/__main__.py` so `python -m invoice_extractor.ui` launches `streamlit run` on the page, and the `ui` optional extra in `pyproject.toml`; verify `pip install -e .[ui]` installs Streamlit and `pytest` still passes in an environment without it
- [x] 3.5 Smoke-test the page with Streamlit's `AppTest` over fixture results (renders rows, session metrics, detail fields, uploader formats), skipped when the extra is absent (PRD 06 R7.2)

## 4. Run it and document it

- [ ] 4.1 **User task (needs API credit):** start the UI, upload one synthetic invoice of each letter plus a negative, and confirm the classification, the fields and the cost shown per document; verify the session total matches the sum of the rows
- [x] 4.2 Add the README "Run the UI" section (install the extra, one command, what the page shows, the spend cap); verify a reader can start it from the README alone. The screenshot waits for task 4.1 (needs credit)
