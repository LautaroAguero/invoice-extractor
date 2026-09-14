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

**Verified (task 3.1):** `bonif` is an **amount**, so the field stays `discount`.
- pyfepdf computes nothing with it. It prints the value it is given in the "Bonif." column (`Item.BonifNN`), through the same number formatter as the unit price (`fmt_pre`, `%0.2f` with Argentine separators) and with no `%` sign.
- In the ARCA item web services the per-line discount is an importe.
- The generator (PRD 02) therefore passes an amount, and V2b is `quantity × unit_price − discount = line_amount`.

**Constraint found in the same source:** pyfepdf's own example writes a *global* discount as a separate item line (`umed=99` "bonificación") with no quantity or price and a negative amount. Such a line would violate the required `quantity`/`unit_price`. The PRD 02 generator should express discounts per line through `bonif`. If global discount lines are wanted later, `quantity` and `unit_price` become optional through a schema change.

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

**Verified (task 2.1, `anthropic` 1.5.0, `pydantic` 2.13.5, request captured with a mock transport):**
- The SDK's `transform_schema` rewrites `oneOf` as `anyOf`.
- It is not a JSON Schema pass-through. It keeps `type`, `enum`, `format` (only `date`, `date-time` and a few others), `minItems` 0/1, `required` and `$ref`/`$defs`. It forces `additionalProperties: false`. Every other keyword is **moved into the description text** and enforced only client-side.
- `Literal["extracted"]` becomes `const`, which is moved to the description. The API grammar would therefore **not** constrain `outcome` at all.
  - **Fix:** annotate each `outcome` as a one-value `enum` (`WithJsonSchema({"type": "string", "enum": ["extracted"]})`), which the SDK keeps.
- The `discriminator` mapping is also moved into the description, as a Python dict repr (noise for the model).
  - **Fix:** a field-level `json_schema_extra` callable drops the key. Client-side validation still uses the discriminator: an unknown outcome fails with `union_tag_invalid`.

### D7 · Encoding: exact decimals as strings, ISO dates, identifiers as unconstrained digit strings

- **Money, quantities, rates, exchange rate:** Python `Decimal`, exposed in the JSON Schema as a string with a machine-format pattern (`^-?\d+(\.\d+)?$`). Descriptions state "digits with a dot as decimal separator, no thousands separator; the document prints 338.650,00, return 338650.00". A JSON number would travel as a float, and whether Pydantic keeps it exactly is unverified.
- **Dates:** `date`, sent as ISO `YYYY-MM-DD`.
- **CUIT, point of sale, invoice number, CAE, document code:** strings described as "digits only, without separators, keeping leading zeros". **No** length or digit patterns. Those formats are business checks (V1, V7). If the grammar forced 14 digits on a misread CAE, the model would pad or invent digits and the misread would be hidden from validation.

The rule: schema patterns constrain *encoding*, never *domain truth*.

**Verified (task 2.1):**
- **A JSON number is lossy.** A bare `Decimal` field emits `anyOf[number, string]`. Pydantic parses a JSON number into `Decimal` through a float: `99999999999999.99` becomes `Decimal('99999999999999.98')` and `12345678901234567.89` becomes `Decimal('12345678901234568')`. String encoding is required, not just preferred.
- **`pattern` is stripped from the grammar.** It is moved into the description, so the API will not stop the model from emitting `"338.650,00"`.
  - Client-side, `Decimal` rejects `"338.650,00"` (`decimal_parsing`) but accepts `"1e3"`. So the money type needs its own validator that enforces the pattern.
  - A violation surfaces as `invalid_output` (D10), which PRD 04 routes to corrective retries.
- **Consequence for implementation:** the money type's JSON Schema is a plain `{"type": "string"}`, and the format rule is written in each field description. A `pattern` would only reach the model as a `{pattern: ...}` suffix in the description, so it adds nothing. The pattern is enforced by the type's validator.
- **Field descriptions on `$ref` properties are dropped.** `transform_schema` returns only `{"$ref": ...}` for a property that references a `$defs` entry. So a `Field(description=...)` on an `Enum`-typed or nested-model-typed field never reaches the model. Implementation consequences:
  - Closed sets are `Literal[...]` types, which are emitted inline with `enum` and keep their description.
  - Nested models (`Issuer`, `Customer`, `Cae`, items) carry their guidance in the class docstring, which lands in `$defs`.
  - Lists keep their description because the `$ref` sits inside `items`.
- `date` is sent as `{"type": "string", "format": "date"}` and kept by the SDK.
- `min_length=1` on a list is sent as `minItems: 1` and kept.
- **Real round-trip (task 2.2, 2026-09-14, `claude-sonnet-5`, `req_011Cf47vhrxCAawAo645HcX5`).** Text input printing Argentine-format amounts, sent through `ModelClient` with a one-value-enum discriminated union, `DecimalString`, `date` and a `minItems: 1` list.
  - The API accepted the schema.
  - The response parsed into the `extracted` branch, with total `Decimal('338650.00')` (exact, not a float), `date(2026, 8, 12)`, and line amounts converted from "150.000,00" to `150000.00`.
  - Call metrics: 1,034 input tokens, 65 output tokens, `end_turn`, 3.1 s, $0.002718. No encoding fallback was needed.

### D8 · Enum values

- `invoice_type`: `A`, `B`, `C`, `E`.
- `currency`: `ARS`, `USD`, `EUR`.
- `vat_condition`: the full ARCA receptor condition list (RG 5616). Values are snake_case forms of the printed labels (`responsable_inscripto`, `consumidor_final`, ...). They are fiscal terms, which the project keeps in Spanish. There is no `other` member: an escape value lets the model skip reading the label. The list is verified against the regulation before it is fixed (task 3).
- `FailureReason`: `not_an_invoice`, `unsupported_document_type`, `illegible`, `missing_mandatory_data`.

**Verified VAT condition list (task 3.2, 2026-09-14):**

| ARCA Id | Printed label | Value | Receptor valid for classes |
|---|---|---|---|
| 1 | IVA Responsable Inscripto | `responsable_inscripto` | A, M, C |
| 4 | IVA Sujeto Exento | `sujeto_exento` | B, C |
| 5 | Consumidor Final | `consumidor_final` | B, C |
| 6 | Responsable Monotributo | `responsable_monotributo` | A, M, C |
| 7 | Sujeto No Categorizado | `sujeto_no_categorizado` | B, C |
| 8 | Proveedor del Exterior | `proveedor_del_exterior` | B, C |
| 9 | Cliente del Exterior | `cliente_del_exterior` | B, C |
| 10 | IVA Liberado – Ley N° 19.640 | `iva_liberado_ley_19640` | B, C |
| 13 | Monotributista Social | `monotributista_social` | A, M, C |
| 15 | IVA No Alcanzado | `iva_no_alcanzado` | B, C |
| 16 | Monotributo Trabajador Independiente Promovido | `monotributo_trabajador_independiente_promovido` | A, M, C |

Sources and their limits:
- **ARCA's developer manual** (RG 4291 – Proyecto FE v4.7, revision 1 September 2026) does not print the table. It points to the web-service method `FEParamGetCondicionIvaReceptor`, which requires an ARCA certificate and was not called. The manual does confirm Id 15 = "IVA No Alcanzado", the field being mandatory under RG 5616, and error 10243 (condition not valid for the invoice class).
- **The full list above comes from a secondary source** (Afip SDK, error 10242 article).
- The same enum is used for the issuer. Issuer labels ("IVA Responsable Inscripto", "Responsable Monotributo", "IVA Sujeto Exento") are a subset.
- The class column is not a schema rule. It can back a PRD 04 check.

### D9 · Client: generic, async, returns a record, never an accumulator

`ModelClient` wraps `AsyncAnthropic` and exposes one operation: given a system prompt, a list of content blocks, an output model and `max_tokens`, it returns a `CallRecord[T]`.

```
CallRecord[T]
  outcome: Parsed[T] | CallFailure(kind, detail)
  model_id, stop_reason, input_tokens, output_tokens,
  cache_read_input_tokens, cache_creation_input_tokens,
  latency_ms, cost_usd, request_id
```

- **Request path, decided 2026-09-14 after task 2.1:**
  1. Call `messages.create` with `output_config={"format": {"type": "json_schema", "schema": anthropic.transform_schema(output_model)}}`.
  2. Check `stop_reason`.
  3. Validate the text block with `TypeAdapter(output_model).validate_json`.

  This is the same schema transform and the same validation `messages.parse` performs, in a different order. `parse` validates inside the call through a post-parser, so on truncated JSON or on a client-side constraint violation it raises `ValidationError` before returning. That loses `usage`, `stop_reason` and `request_id`, which D10 requires. The async raw-response wrapper has no `parse` method to recover them.
  - *Alternatives considered:* keep `parse` and capture the raw body with an `httpx2` response hook plus a per-call contextvar (fragile, tied to SDK internals, awkward under concurrency); or keep `parse` and drop metrics on those failures (breaks CC-3).
- It knows nothing about invoices. `ModelFailure` (the schema's `Failed` branch) is a `Parsed` outcome from the client's point of view; the extraction layer interprets it.
- Latency is wall clock around the SDK call, including SDK transport retries.
- It holds no cumulative state. Aggregation and spend caps belong to the PRD 03 runner.
- The SDK dependency is injected (a narrow protocol over `messages.create`), so tests use a fake with no API key.

*Alternative considered:* raising exceptions for truncation and refusal, as the course client does. Rejected: PRD 03 runs many documents and needs a per-document outcome, and PRD 01 R2.4 asks for typed failures, not crashes.

### D10 · Call-site failure handling

There is one model call site in this change (`ModelClient.call`, used by the single-document extraction).

| Condition | Handling | Outcome |
|---|---|---|
| 429 rate limit, 529 overloaded, 5xx, connection error, timeout | SDK transport retries with exponential backoff; `max_retries` and `timeout` from config (default 3 and 120 s), never unbounded | If retries run out: `CallFailure(api_error)` with the status/exception type; the record keeps latency and zero tokens |
| 400 bad request (e.g. PDF too large, schema rejected) | Not retried | `CallFailure(api_error)` |
| 401/403 authentication/permission, 404 unknown model | Not retried; **raised** | Configuration error: every later call would fail the same way, so the run must stop rather than record N failures |
| `stop_reason == "max_tokens"` | Checked **before** reading the parsed output. With adaptive thinking the cut usually happens mid-thinking, before any JSON exists | `CallFailure(truncated)`; tokens and cost recorded |
| `stop_reason == "refusal"` | Checked before the parsed output | `CallFailure(refused)`; tokens and cost recorded |
| Output fails client-side validation (stripped constraints, `min 1 item`, decimal pattern), or no text block is present | `ValidationError` from validating the text **after** the stop-reason check (D9 request path) | `CallFailure(invalid_output)` with the validation errors; tokens and cost recorded. PRD 04 R2.3 routes this into corrective retries |
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

Rendered files stay in the gitignored `tools/generate_invoices/out/`. Unit tests never need PDFs, because they use the fake client. **Verified (task 3.3):** pyfepdf maps `tipo_cbte` to its title and code. `spike_factura_a.py --tipo-cbte 3` renders a nota de crédito A: title "Nota de Crédito", `COD.03`, everything else identical to the Factura A (same number, CAE and amounts). That makes it a hard negative that differs from the invoice only in its title and code.

## Measured calls (tasks 2.2 and 8.1–8.4)

Measured on 2026-09-14 with `claude-sonnet-5`, prompt `v1`, price table verified 2026-09-14. One call per document, so these are single observations, not distributions.

| Task | Document | Outcome | Input tok | Output tok | Stop reason | Latency | Cost | Request ID |
|---|---|---|---|---|---|---|---|---|
| 8.1 | Spike Factura A (1 page) | extracted, identical to the hand-built fixture | 9,404 | 1,114 | `end_turn` | 15.3 s | $0.029948 | `req_011Cf47x2sydUtxHAbASk5DP` |
| 8.2 | Spike nota de crédito A | failed: `unsupported_document_type` | 9,409 | 61 | `end_turn` | 3.2 s | $0.019428 | `req_011Cf47zE7TjLtX6sZrLPg3R` |
| 8.3 | One-page meeting minutes (non-invoice) | failed: `not_an_invoice` | 8,894 | 66 | `end_turn` | 3.0 s | $0.018448 | `req_011Cf47zZfCaLXYo9kRQtn2L` |
| 8.4 | Spike Factura A, `--max-tokens 64` | call failure: `truncated` | 9,404 | 64 | `max_tokens` | 2.9 s | $0.019448 | `req_011Cf47ztRKANcKzXnHeykUy` |
| 2.2 | Short text, small spike schema | extracted | 1,034 | 65 | `end_turn` | 3.1 s | $0.002718 | `req_011Cf47vhrxCAawAo645HcX5` |

Compared with the earlier estimates (input 4–6k, output 1.5–4k, $0.02–0.05, 10–30 s):

- **Input is about double the estimate** (~9.4k tokens). The invoice and the meeting minutes, both one page, differ by only ~500 tokens. So most of the input is likely a per-call fixed prefix: system prompt, the ~14 KB result schema, and the API's structured-output overhead.
  - *Inference, not measured:* the split has not been counted. PRD 04 can count it with the token-counting endpoint.
  - If confirmed, the prefix is well above the cacheable minimum, so prompt caching (PRD 04 R5.3) applies. Input is already about two thirds of the extraction cost.
- **Output for a 3-item extraction is 1,114 tokens.** That includes any adaptive thinking, which is billed in `output_tokens`. Rejections cost ~60 output tokens.
- **An extraction costs ~$0.030 and takes ~15 s.** A rejection costs ~$0.019 and takes ~3 s, dominated by input.
- **For a 30-document run**, assuming these per-call numbers hold, the order of magnitude is ~$0.90 and ~7.5 min sequentially. This is an extrapolation from single calls on one-page documents. Multi-page and dense documents will cost more.

## Risks / Trade-offs

- [The SDK sends `Decimal` or the union in a form the API rejects or loses precision on] → Task 2 is a spike before any schema work. The fallbacks are in D6 and D7.
- [Many optional fields make `null` the easy answer, which inflates field precision (measurement 2a)] → Invented/missed counts are always reported (measurement rules). Descriptions say `null` only when not printed.
- [`missing_mandatory_data` becomes a way out on hard documents] → Narrow definition (D5). False rejections are a headline line in PRD 03.
- [Adaptive thinking inflates output tokens] → Recorded as measured cost. Effort tuning is a PRD 04 lever.
- [Forced truncation can land mid-thinking, so the truncation test does not exercise a half-written JSON] → The typed failure is the same either way. An API-free test covers the fake `max_tokens` path explicitly.
- [Enum without `other` rejects an unusual VAT condition label] → The full regulatory list is used. If a real label is missing, the output fails validation visibly instead of being coerced.
- [Schema has more fields than the PRD 01 table, so there is more to extract and score] → Each addition is justified by a check or by representability (D2, D3, D4). Scoring rules for the new lists are an open question.

## Open Questions

- **List scoring for `vat_breakdown` and `other_taxes`** (recorded as PRD 03 OQ-3.2). `measurement-rules.md` defines only `items`. Options: by position like items, by rate/description, or as a multiset. Stage 1 does not score anything, so this does not change these specs or tasks. It must go through the measurement change log before the PRD 03 baseline.
- **Transport-retry count per call.** Measurement §5 records transport retries separately. The SDK does not return the count directly. Deferred to PRD 03, where it is needed; stage 1 records latency only.
