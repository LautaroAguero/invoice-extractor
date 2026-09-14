## Why

Nothing can be measured or hardened until one invoice goes in and one typed, schema-valid result comes out, with its cost and latency recorded. Stage 1 builds that path with a plain v1 prompt, so the later baseline is honest. It also fixes the result schema early, because the stage 2 ground truth has to validate against it (PRD 02 R3.2) and the stage 4 business checks depend on the fields it carries.

Stage PRD: [PRD 01 · Happy path](../../../docs/prd/01-happy-path.md).

## What Changes

- New Python package for the extractor (kept separate from `tools/generate_invoices/`, which it never imports).
- **Result schema** (Pydantic): a top-level result that is either an extracted invoice or a failure with a typed reason (`not_an_invoice`, `unsupported_document_type`, `illegible`, `missing_mandatory_data`). Every field carries a description with its printed Spanish label.
- The schema shape decided during exploration differs from the PRD 01 initial field table:
  - Totals that the document does not print are optional and `null` (`net_amount`, `vat_amount`, `items[].vat_rate`). `currency` stays required, with "ARS when the document shows no currency" as a convention.
  - The total follows the WSFE formula: new `non_taxed_amount`, `exempt_amount` and `other_taxes[]`.
  - Items gain an optional `discount` ("Bonif."). Unit and per-line VAT amount stay out.
  - New `document_code` (printed "COD.NN"), redundant with the invoice letter.
  - Mandatory fields are exactly what every ARCA invoice has to print. `customer.name` is optional.
- **Model client** (async, native structured outputs): sends content blocks, returns a per-call record with outcome, model ID, tokens (including cache), stop reason, latency and cost from `usage`. Truncation, refusal and API errors become typed call failures and are never returned as parsed objects.
- **Price and model configuration** with the date prices were verified.
- **Prompt** `prompts/extract_invoice/v1.md`: minimal instructions in the system prompt, document in the user turn.
- A single-document extraction entry point run against the spike Factura A and a negative (the same spike rendered as a nota de crédito).
- Follow-up edits to PRD 01, PRD 02 and PRD 04 so they reflect the decisions above.

## Capabilities

### New Capabilities

- `invoice-schema`: the extraction result contract. Covers the extracted/failed outcomes, failure reasons, invoice fields, which fields are mandatory or optional, encoding of amounts and dates, and field descriptions.
- `model-client`: an instrumented, failure-aware async call to the model with native structured outputs. Covers per-call records, cost computation, typed call failures, transport retries and model/price configuration.
- `invoice-extraction`: extracting one document. Covers the versioned prompt, message layout (system prompt vs user turn) and the extraction entry point that ties schema, prompt and client together.

### Modified Capabilities

None. `openspec/specs/` is empty.

## Requirements covered

- PRD 01 R1, R1.1–R1.6 (schema)
- PRD 01 R2, R2.1–R2.7 (model client)
- PRD 01 R3, R3.1–R3.2 (prompt)
- Cross-cutting: CC-1, CC-2, CC-3, CC-4, CC-6, CC-7, CC-8. CC-5 is satisfied by construction for a single call; the per-run cap is deferred to PRD 03 (design D14).

## Open questions this change depends on

| ID | Question | Status |
|---|---|---|
| OQ-1.1 | Baseline model | Resolved 2026-09-14: `claude-sonnet-5` |
| OQ-1.2 | Derive or extract `vat_breakdown` | Resolved 2026-09-14: extracted |
| OQ-2.1 | Nota de crédito in scope or negative | Resolved 2026-09-14 during exploration: **(a) out of scope**. Notas de crédito/débito and factura M are negatives with reason `unsupported_document_type`. PRD 02 still has to record this. |
| New | How `vat_breakdown` and `other_taxes` lists are scored. `measurement-rules.md` only defines `items`. | **Open.** Does not block stage 1; must go through the measurement change log before the PRD 03 baseline. |
| New | Whether the stage 1 single-call script needs a CC-5 spend cap | Resolved 2026-09-14: bounded by `max_tokens` and `max_retries`; the per-run cap is deferred to the PRD 03 runner |

## Impact

- New code: extractor package (schema, client, extraction), `prompts/extract_invoice/v1.md`, pricing/model configuration, `.env.example`, and tests that never call the API.
- New dependencies: `anthropic`, `pydantic`, `python-dotenv`, `pytest`.
- Docs: PRD 01 (field table, R1.2 optional list), PRD 02 (OQ-2.1, R2 negatives table, R3.1 currency convention), PRD 04 (V3 formula, new V2b line arithmetic check).
- Generator: one extra spike render (nota de crédito) in `tools/generate_invoices/`, which stays isolated.
