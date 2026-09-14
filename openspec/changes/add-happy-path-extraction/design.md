## Context

See proposal.md for motivation and scope. Current state:

- The repo holds PRDs, measurement rules and a generator spike (`tools/generate_invoices/spike_factura_a.py`). It renders one Factura A with pyfepdf. The extractor has no code yet.
- The spike PDF has a text layer. Its printed layout drives several schema decisions below:
  - Money is printed in Argentine format (`338.650,00`).
  - The "IVA" item column glues rate and amount together (`21%31.500,00`).
  - Totals show `No Gravado`, `Exento`, `Neto`, one `IVA` line per rate, and `Total`.
  - There is no currency label. The document code is printed as `COD.01`.
  - `IIBB 30712345671` is printed next to the issuer CUIT and is identical to it.
- The course reference client (`ai-engineer-lab/practice/llm_client.py`) is a starting point to move away from, not to reuse. It parses free text, is sync, keeps a global usage accumulator and silently falls back to Opus prices for unknown models.
- Verified platform facts and pricing are listed in `docs/prd/00-overview.md`. They are re-verified by task 2 before the schema is built on them.

## Goals / Non-Goals

**Goals:**
- Fix a result schema that later stages can build ground truth and business checks on without reshaping it.
- Make every call observable and every failure typed, so PRD 03 can aggregate per-document numbers without touching the client.
- Keep the client generic over the output model, so the invoice domain never leaks into it (CC-2).

**Non-Goals:**
- Business validation, corrective retries, spend caps per run (PRD 03/04).
- Text-layer or image ingestion (PRD 03). The content-block API allows them, but only PDF is wired.
- Prompt quality. v1 is deliberately plain.
- Recording transport-retry counts per call. See Open Questions.

## Decisions

### D1 · Fields the document does not print are optional and `null`

`net_amount`, `vat_amount`, `non_taxed_amount`, `exempt_amount`, `items[].vat_rate` and `items[].discount` are optional. B and C invoices do not print net or VAT, and ground truth is what is visible (PRD 02 R3.1). A required field would force the model to compute a value, which the measurement rules count as an invented value.

Lists (`vat_breakdown`, `other_taxes`) are required but empty when nothing is printed, so there is a single representation of "none".

**Exception:** `currency` is required. Its description states "ARS when the document shows no currency". This is the fiscal convention, not an inference, and it keeps ground truth unambiguous. PRD 02 R3.1 must record the exception (task 11).

*Alternative considered:* required fields derived by the model (net = total − VAT). Rejected: it moves arithmetic into extraction, which is PRD 04 territory, and hides misreads.

### D2 · Totals follow the WSFE formula

`total = net_amount + non_taxed_amount + exempt_amount + vat_amount + sum(other_taxes.amount)`, with absent terms treated as zero by the validator (PRD 04, not here). `other_taxes` is a list of `{description, amount}` because ARCA tributes are an array (percepciones, impuestos internos), each printed on its own line. The global "Descuento" printed under the table is out: it is not a term of the total.

*Alternative considered:* keep PRD 01's `net + vat = total` and add fields as a PRD 04 iteration. Rejected: PRD 02 R3.2 requires ground truth to validate against the schema, so a later change would mean relabelling the dataset. A missing field is not a variable to tune; the schema simply cannot represent the document.

### D3 · Item fields: included only when a check needs them

The rule: an item field is included only when a business check needs it or it creates a verifiable redundancy. Items are scored all-or-nothing (measurement §3), so every extra field makes items harder to get right.

| Field | Printed label | Why |
|---|---|---|
| `code` (optional) | Articulo | identity, cheap |
| `description` | Descripción | identity |
| `quantity`, `unit_price` | Cantidad, Precio | line arithmetic |
| `discount` (optional) | Bonif. | closes `quantity × unit_price − discount = line_amount` (new check V2b) |
| `vat_rate` (optional) | IVA (rate part) | V4 base per rate |
| `line_amount` | Importe | V2 |

Out: unit (`Unid.`) and per-line VAT amount. Neither feeds a check. Reading `vat_rate` already exercises the glued column.

Whether pyfepdf's `bonif` is an amount or a percentage is unverified (task 3). If it is a percentage, the field becomes `discount_rate` and V2b changes accordingly.

### D4 · Document types: invoices only, and a dedicated failure reason

`invoice_type` is A/B/C/E. Notas de crédito/débito and factura M are out of scope and must produce the failure reason `unsupported_document_type` (OQ-2.1 resolved as option a). That reason is kept separate from `not_an_invoice`: both count as explicit failures under the measurement rules, but failure analysis needs to tell "did not recognise the document" apart from "recognised a nota de crédito and correctly declined".

`document_code` (optional, digits of the printed "COD.NN") is added. It is redundant with the letter, so the PRD 04 checks can compare them. It also gives the model a second cue besides the title when declining a nota de crédito. It is optional because it was not part of the agreed mandatory list (D5).

### D5 · Mandatory means "every ARCA invoice prints it"

Required: `invoice_type`, `point_of_sale`, `invoice_number`, `issue_date`, `issuer.{name, cuit, vat_condition}`, `customer.vat_condition`, `currency`, `total`, `cae.{number, expiry_date}`, and `items` with at least one element.

Optional: `customer.{name, cuit, address}`, `due_date`, `exchange_rate`, `document_code`, plus the D1 and D3 optionals.

Mandatory fields map 1:1 to the `missing_mandatory_data` reason. If the document is an invoice but a mandatory field cannot be read, the model returns that failure naming the field and never fills it in. This keeps the reason narrow enough that it cannot become a way to avoid committing, but still an honest way out.

The minimum of one item is stated in the description and checked client-side. JSON Schema `minItems` support in structured outputs is unverified (task 2).

### D6 · Result envelope: discriminated union under a root object

```
ExtractionResult { result: Extracted | Failed }   discriminator: outcome
  Extracted { outcome: "extracted", invoice: Invoice }
  Failed    { outcome: "failed", reason: FailureReason, detail: str }
```

The root has to be an object, so the union sits under `result`. The flat alternative (`outcome`, `invoice?`, `failure?`) lets both or neither be set and moves the invariant into client code. The discriminated union makes invalid combinations unrepresentable.

The PRD 01 risk "maximum 2 levels of nesting" is read as applying to the invoice (`invoice > issuer.cuit`), not to the envelope.

**To verify (task 2):** Pydantic emits `oneOf` plus a `discriminator` mapping. Confirm what the SDK transforms that into and that the API accepts it. Fallback: plain `anyOf` with a literal `outcome` on each branch, which Pydantic still validates as discriminated client-side.

### D7 · Encoding: exact decimals as strings, ISO dates, identifiers as unconstrained digit strings

- **Money, quantities, rates, exchange rate:** Python `Decimal`, exposed in the JSON Schema as a string with a machine-format pattern (`^-?\d+(\.\d+)?$`). Descriptions state "digits with a dot as decimal separator, no thousands separator; the document prints 338.650,00, return 338650.00". A JSON number would travel as a float, and whether Pydantic keeps it exactly is unverified.
- **Dates:** `date`, sent as ISO `YYYY-MM-DD`.
- **CUIT, point of sale, invoice number, CAE, document code:** strings described as "digits only, without separators, keeping leading zeros". **No** length or digit patterns. Those formats are business checks (V1, V7). If the grammar forced 14 digits on a misread CAE, the model would pad or invent digits and the misread would be hidden from validation.

The rule: schema patterns constrain *encoding*, never *domain truth*.

**To verify (task 2):** what the SDK sends for this annotated `Decimal` and for `date`, whether `pattern` survives or is stripped and re-validated client-side, and that a real response round-trips `338650.00` exactly.

### D8 · Enum values

- `invoice_type`: `A`, `B`, `C`, `E`.
- `currency`: `ARS`, `USD`, `EUR`.
- `vat_condition`: the full ARCA receptor condition list (RG 5616). Values are snake_case forms of the printed labels (`responsable_inscripto`, `consumidor_final`, ...). They are fiscal terms, which the project keeps in Spanish. There is no `other` member: an escape value lets the model skip reading the label. The list is verified against the regulation before it is fixed (task 3).
- `FailureReason`: `not_an_invoice`, `unsupported_document_type`, `illegible`, `missing_mandatory_data`.

### D9 · Client: generic, async, returns a record, never an accumulator

`ModelClient` wraps `AsyncAnthropic` and exposes one operation: given a system prompt, a list of content blocks, an output model and `max_tokens`, it returns a `CallRecord[T]`.

```
CallRecord[T]
  outcome: Parsed[T] | CallFailure(kind, detail)
  model_id, stop_reason, input_tokens, output_tokens,
  cache_read_input_tokens, cache_creation_input_tokens,
  latency_ms, cost_usd, request_id
```

- It knows nothing about invoices. `ModelFailure` (the schema's `Failed` branch) is a `Parsed` outcome from the client's point of view; the extraction layer interprets it.
- Latency is wall clock around the SDK call, including SDK transport retries.
- It holds no cumulative state. Aggregation and spend caps belong to the PRD 03 runner.
- The SDK dependency is injected (a narrow protocol over `messages.parse`), so tests use a fake with no API key.

*Alternative considered:* raising exceptions for truncation and refusal, as the course client does. Rejected: PRD 03 runs many documents and needs a per-document outcome, and PRD 01 R2.4 asks for typed failures, not crashes.

### D10 · Call-site failure handling

There is one model call site in this change (`ModelClient.parse`, used by the single-document extraction).

| Condition | Handling | Outcome |
|---|---|---|
| 429 rate limit, 529 overloaded, 5xx, connection error, timeout | SDK transport retries with exponential backoff; `max_retries` and `timeout` from config (default 3 and 120 s), never unbounded | If retries run out: `CallFailure(api_error)` with the status/exception type; the record keeps latency and zero tokens |
| 400 bad request (e.g. PDF too large, schema rejected) | Not retried | `CallFailure(api_error)` |
| 401/403 authentication/permission, 404 unknown model | Not retried; **raised** | Configuration error: every later call would fail the same way, so the run must stop rather than record N failures |
| `stop_reason == "max_tokens"` | Checked **before** reading the parsed output. With adaptive thinking the cut usually happens mid-thinking, before any JSON exists | `CallFailure(truncated)`; tokens and cost recorded |
| `stop_reason == "refusal"` | Checked before the parsed output | `CallFailure(refused)`; tokens and cost recorded |
| Output fails client-side validation (stripped constraints, `min 1 item`, decimal pattern) | Caught `ValidationError` | `CallFailure(invalid_output)` with the validation errors; tokens and cost recorded. PRD 04 R2.3 routes this into corrective retries |
| Unknown model ID in the price table | Checked **before** the call | Raised (configuration error), never a silent default price |

### D11 · Cost and configuration

`cost_usd = (input × in + output × out + cache_read × in × cache_read_mult + cache_write × in × cache_write_mult) / 1e6`. Thinking tokens are included in `output_tokens`.

Model ID, `max_tokens`, timeout, `max_retries` and the price table (per model: input, output, cache multipliers, `verified_on` date) live in a committed config file. The API key comes from the environment (`.env`, ignored; `.env.example` committed).

Baseline `max_tokens`: 16,000. That leaves room for adaptive thinking plus a long item list, and it bounds a single call's output cost at $0.16 on Sonnet 5.

### D14 · CC-5 in stage 1: bounded by construction, per-run cap deferred

Decided with the user on 2026-09-14. The single-document entry point makes exactly one model call with no corrective retries, so its spend is bounded by input size plus `max_tokens` (≤ $0.16 output on Sonnet 5). Transport retries can repeat the call, but they are capped by `max_retries`. No explicit USD cap is built in this change. The per-run spend cap and the per-document attempt cap are built with the PRD 03 runner, where a run spans many documents.

### D12 · Prompt and message layout

- `prompts/extract_invoice/v1.md` is loaded by version. A missing version is an error, never a fallback.
- The system prompt holds the instructions (role, task, use the failure outcome when the document is not a supported invoice or a mandatory value is not visible, never guess). The user turn holds only the document block, so the fixed prefix can be cached later.
- The prompt version travels with the result, so PRD 03 run records can cite it.

### D13 · Negative fixture for acceptance

The acceptance run uses two negatives:
- The spike rendered with `tipo_cbte=3` (nota de crédito A), expected `unsupported_document_type`.
- Any one-page non-invoice PDF, expected `not_an_invoice`.

Rendered files stay in the gitignored `tools/generate_invoices/out/`. Unit tests never need PDFs, because they use the fake client. Whether pyfepdf changes the printed title for `tipo_cbte=3` is verified in task 3.

## Estimates (ESTIMATED, not measured; replaced by task 10 numbers)

| Metric | Estimate for the 1-page spike on `claude-sonnet-5` | Basis |
|---|---|---|
| Input tokens | 4,000–6,000 | ~1,500–3,000 text tokens per PDF page plus the page image, ~400 system prompt, plus schema overhead |
| Output tokens | 1,500–4,000 | ~800–1,200 for the JSON with 3 items, plus adaptive thinking of unknown size |
| Cost per document | $0.02–0.05 | $2 / $10 per MTok |
| Latency | 10–30 s | adaptive thinking plus PDF processing; no measurement yet |

## Risks / Trade-offs

- [The SDK sends `Decimal` or the union in a form the API rejects or loses precision on] → Task 2 is a spike before any schema work. The fallbacks are in D6 and D7.
- [Many optional fields make `null` the easy answer, which inflates field precision (measurement 2a)] → Invented/missed counts are always reported (measurement rules). Descriptions say `null` only when not printed.
- [`missing_mandatory_data` becomes a way out on hard documents] → Narrow definition (D5). False rejections are a headline line in PRD 03.
- [Adaptive thinking inflates output tokens] → Recorded as measured cost. Effort tuning is a PRD 04 lever.
- [Forced truncation can land mid-thinking, so the truncation test does not exercise a half-written JSON] → The typed failure is the same either way. An API-free test covers the fake `max_tokens` path explicitly.
- [Enum without `other` rejects an unusual VAT condition label] → The full regulatory list is used. If a real label is missing, the output fails validation visibly instead of being coerced.
- [Schema has more fields than the PRD 01 table, so there is more to extract and score] → Each addition is justified by a check or by representability (D2, D3, D4). Scoring rules for the new lists are an open question.

## Open Questions

- **List scoring for `vat_breakdown` and `other_taxes`.** `measurement-rules.md` defines only `items`. Options: by position like items, by rate/description, or as a multiset. Stage 1 does not score anything, so this does not change these specs or tasks. It must go through the measurement change log before the PRD 03 baseline.
- **Transport-retry count per call.** Measurement §5 records transport retries separately. The SDK does not return the count directly. Deferred to PRD 03, where it is needed; stage 1 records latency only.
