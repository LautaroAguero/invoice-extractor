# PRD 01 · Happy path

Status: draft · Stage 1 of 5 · Depends on: nothing · Course estimate: ~2 h

## Why

Before building a dataset or an evaluation harness, prove the central piece works end to end: one invoice goes in and one typed, schema-valid object comes out, with its cost and latency recorded. Everything later measures and hardens this path, so it has to exist first.

## Scope

**In**
- The invoice schema (initial version).
- A model client that sends a PDF as a document block and returns a parsed object plus usage metadata.
- A single extraction call over one synthetic invoice (the spike output from `tools/generate_invoices/`).
- An explicit "not an invoice / cannot extract" outcome inside the schema.

**Out** (later stages)
- Business validation and corrective retries (PRD 04).
- Text-extraction ingestion path, image input (PRD 03).
- CLI, batch processing, report (PRD 03, PRD 05).
- Any prompt tuning. Stage 1 uses a plain v1 prompt on purpose, so the baseline is honest.

## Requirements

### R1 · Schema

The schema must meet the course minimum: at least 8 fields, 2 nested objects, 1 list of items, 1 enum and 2 optional fields. It must also:

- **R1.1** Use enums wherever the domain is closed: invoice type (A, B, C, E), currency, VAT condition.
- **R1.2** Mark as optional every field that can legitimately be missing from a real invoice: customer CUIT on a B to a final consumer, due date, customer address, exchange rate.
- **R1.3** Carry an escape hatch at the top level: a result that is either an extracted invoice or a failure with a reason (not an invoice, illegible, missing mandatory data). A model with no way to fail invents data.
- **R1.4** Give every field a description. Descriptions name the literal Spanish label printed on the document when there is one ("CUIT del emisor", "Fecha de Vto. CAE").
- **R1.5** Avoid a free-form "confidence" field. Model-reported confidence is not calibrated (course 5.6).
- **R1.6** Money is exact decimal and dates are ISO dates in the parsed object. How they are encoded in the JSON Schema is a design decision; verify what the SDK sends for `Decimal`.

Initial field set (proposal; the OpenSpec design owns the final shape):

| Field | Type | Notes |
|---|---|---|
| `invoice_type` | enum A/B/C/E | printed letter + code |
| `point_of_sale`, `invoice_number` | string | "00003-00001542" split in two |
| `issue_date` | date | not the CAE expiry, not the due date |
| `due_date` | date, optional | |
| `issuer` | nested: name, CUIT, VAT condition | |
| `customer` | nested: name, CUIT (optional), address (optional), VAT condition | |
| `currency` | enum ARS/USD/EUR | |
| `exchange_rate` | decimal, optional | only for foreign currency |
| `items` | list: code (optional), description, quantity, unit price, VAT rate, line amount | |
| `vat_breakdown` | list: rate, amount | empty for B/C |
| `net_amount`, `vat_amount`, `total` | decimal | |
| `cae` | nested: number, expiry date | |

### R2 · Model client

- **R2.1** Accepts content blocks: a PDF document block now, text and image blocks later.
- **R2.2** Uses native structured outputs (`messages.parse` with the Pydantic result model). No JSON parsing from free text.
- **R2.3** Returns, per call: parsed object (or typed failure), model ID, input/output/cache tokens, stop reason, latency in ms, cost in USD. It keeps no hidden global accumulator (the evaluation needs per-document numbers).
- **R2.4** Handles `stop_reason` of `max_tokens` (truncated) and `refusal` as explicit, typed failures, never as a parsed object.
- **R2.5** Transport retries (429, 5xx, timeouts) come from the SDK with a ceiling, and are distinct from the corrective retries of PRD 04.
- **R2.6** Model ID and the price table are configuration, with the date the prices were verified.
- **R2.7** Async-capable (`AsyncAnthropic`), so PRD 03 can run a dataset with bounded concurrency.

Reference: `ai-engineer-lab/practice/llm_client.py` (course chapter 3) is the starting point. As it stands it violates R2.1, R2.2, R2.3 and R2.7.

### R3 · Prompt

- **R3.1** `prompts/extract_invoice/v1.md` is minimal: role, task, "use the failure outcome when the document is not an invoice or a value is not present; never guess".
- **R3.2** The document goes in the user turn and the instructions in the system prompt, so the fixed prefix stays cacheable later.

## Acceptance criteria

- [ ] Running the extraction on the spike invoice returns an object whose total, issuer CUIT, customer CUIT, invoice number and CAE match the rendered values.
- [ ] Running it on a non-invoice PDF (any one-page non-invoice document) returns the failure outcome with a reason, not an invoice.
- [ ] The call prints model, tokens in/out, stop reason, latency and cost; cost is computed from `usage`.
- [ ] A truncated response (forced via a tiny `max_tokens`) produces a typed failure, not a crash and not a partial object.
- [ ] The schema meets the course minimum (≥8 fields, 2 nested, 1 list, 1 enum, 2 optional).
- [ ] No API key or generated personal data is committed.

## Risks

| Risk | Mitigation |
|---|---|
| `Decimal`/`date` JSON Schema encoding differs from expectations, so parsing fails or values arrive as floats | Verify the schema the SDK sends in stage 1, before building on it |
| Sonnet 5 adaptive thinking (on by default) inflates output cost for a simple extraction | Record thinking in output tokens; effort tuning is a PRD 04 iteration, not a stage 1 change |
| Schema too deep hurts quality and retries | Maximum 2 levels of nesting |

## Open questions

- ~~OQ-1.1 Baseline model~~ resolved 2026-09-14: `claude-sonnet-5`. Verified behavior to respect: adaptive thinking runs when `thinking` is omitted; `temperature`/`top_p`/`top_k` are rejected with 400, so non-determinism is controlled through fixed prompts and schema, never through sampling parameters; `budget_tokens` is rejected; native structured outputs are supported.
- ~~OQ-1.2 Derive or extract `vat_breakdown`~~ resolved 2026-09-14: the model **extracts** it. Keeping it as an extracted field preserves the redundancy that business check V4 (PRD 04) uses to detect invented or misread amounts.
