# invoice-extractor

Extracts Argentine invoices (types A, B, C and E) into structured, validated objects, and **measures
its own reliability and its cost per document**. The measurement is the product: an extractor
without measured per-field accuracy and per-document cost is not finished.

> Status: stages 1 to 3 are complete (extraction, a synthetic dataset of 30 documents, the
> evaluation harness). The local UI already works. Stages 4 and 5 (business validation with
> corrective retries, and the CLI plus the final README with the iteration log) are planned in
> `openspec/changes/`. This README is provisional: stage 5 rewrites it with the results and the log.

## The local UI

A single-user page on your own machine: upload an invoice and see how it gets classified, what gets
extracted, and what the call cost.

```bash
pip install -e .[ui]
```

```bash
python -m invoice_extractor.ui
```

It opens at `http://localhost:8501`. You need `ANTHROPIC_API_KEY` in the environment or in a `.env`
file (copy `.env.example`). Each invoice costs about USD 0.04 with Sonnet 5 and USD 0.01 with
Haiku 4.5.

What it shows:

- **Classification:** the document type (A, B, C or E), or an explicit failure with its reason. A
  failure is never shown as a half-filled invoice.
- **Cost and performance:** cost in USD computed from the call's actual `usage`, input and output
  tokens, latency and attempts. None of the numbers are estimates.
- **Every field:** issuer, customer, dates, line-item table, VAT breakdown, totals and CAE, next to
  the document, plus the raw JSON.

In the sidebar you pick the model (among those priced in `config/extractor.toml`), the prompt
version and the **session spend cap**, which cannot be disabled and is checked before every
document.

Accepted formats: PDF, JPG and PNG. Anything else is rejected before the model is called. Uploaded
files are processed in a temporary directory outside the repository and deleted as soon as they are
processed; nothing is kept.

## From the terminal

```bash
python -m invoice_extractor.extract_one ground_truth/A01.pdf
```

```bash
python -m invoice_extractor.evaluate --path a --spend-cap 3
```

The first extracts one document and prints the result with its cost. The second runs the full
dataset, saves the run record in `runs/` and shows the quality report. To re-render a report
without calling the model: `python -m invoice_extractor.report_cli`.

## Tests

```bash
pytest
```

They pass without `ANTHROPIC_API_KEY` set and without network access: no test calls the API.

## Layout

| Folder | Contents |
|---|---|
| `src/invoice_extractor/` | The extractor: schema, model client, extraction, evaluation and UI |
| `ground_truth/` | The 30 synthetic documents with their ground truth and the manifest |
| `tools/generate_invoices/` | The dataset generator (GPL-3.0, its own venv, never imported by the extractor) |
| `docs/prd/` | One PRD per stage, plus the overview |
| `docs/` | Measurement rules, quality report and failure analysis |
| `openspec/` | Current specs and in-progress changes |
| `runs/` | Run records from each evaluation run |

## Known limitations

- The measured dataset is 100% synthetic: accuracy on real invoices has not been measured.
- With n=30, a single run has a noise floor of about ±9 points, and two runs cannot be told apart
  below about ±12.6 points.
- It does not validate CUIT or CAE against ARCA's records.
- The UI is local and single-user. There is no deployment and no authentication.
