## 1. Project setup

- [x] 1.1 Create the extractor package layout (`src/invoice_extractor/`, `tests/`, `prompts/extract_invoice/`, config file) with `pyproject.toml` declaring `anthropic`, `pydantic`, `python-dotenv` and `pytest`; verify `pip install -e .` succeeds in a fresh venv separate from `tools/generate_invoices/.venv`
- [x] 1.2 Add `.env.example` with `ANTHROPIC_API_KEY=` and an empty placeholder test; verify `pytest` passes with `ANTHROPIC_API_KEY` unset and `git status` shows no `.env` tracked

## 2. Encoding spike (before any schema work)

- [x] 2.1 Build throwaway Pydantic models covering an annotated `Decimal` (string plus pattern), a `date`, a `min 1` list and a discriminated union under a root object. Capture the request body the SDK sends for `messages.parse`, using an `httpx.MockTransport` (no API call). Verify by writing into design.md D6/D7 what the SDK transforms `oneOf`/discriminator, `pattern`, `format: date` and `minItems` into, and which constraints are stripped and validated client-side
- [ ] 2.2 Make one real `claude-sonnet-5` call with the spike models on a tiny text prompt that must return `338650.00` and an ISO date. Verify the parsed `Decimal` equals `Decimal("338650.00")` exactly and is not a float, and that the union parses into the right branch; record the result (or the fallback taken) in design.md D6/D7

## 3. Domain verifications

- [x] 3.1 Check in pyfepdf's source and rendered output whether `bonif` is an amount or a percentage; verify by recording the answer in design.md D3 (and renaming to `discount_rate` there if it is a percentage)
- [x] 3.2 Verify the full ARCA receptor VAT condition list against RG 5616 and record the exact labels and snake_case values in design.md D8
- [x] 3.3 Add a `--tipo-cbte` option to `tools/generate_invoices/spike_factura_a.py` and render the spike as a nota de crédito A (`tipo_cbte=3`); verify by opening the PDF that the title reads "Nota de Crédito" and the code reads `COD.03` (if pyfepdf does not change the title, record it in design.md D13 and adjust the template CSV)

## 4. Result schema

- [x] 4.1 Implement the result envelope (`outcome` discriminator, `Extracted`, `Failed`, `FailureReason`) using the encoding confirmed in task 2; verify with API-free tests for the extracted, failed, mixed-rejected and unknown-reason scenarios
- [x] 4.2 Implement the invoice, party, CAE, item, VAT breakdown and other-tax models with the D5 mandatory/optional split and the D8 enums; verify with tests for missing mandatory field, empty items, consumer invoice without identity, Factura B with `null` net/VAT, omitted list, unsupported letter and catch-all VAT condition
- [x] 4.3 Implement exact decimal and identifier encoding; verify with tests: `"338650.00"` parses exactly and not as float, `"338.650,00"` is rejected, `"00003"` keeps its zeros, a 13-digit CAE still validates, and an inconsistent total still validates
- [x] 4.4 Write every field description with its printed Spanish label and the `null`-when-not-printed and ARS conventions; verify with schema-introspection tests: every property has a non-empty description, no confidence/score property, invoice nesting ≤ 2 object levels, course minimum met
- [x] 4.5 Build the spike Factura A as a schema instance by hand from the PDF (visible values); verify it validates, and commit it as a test fixture (synthetic data only)

## 5. Configuration and cost

- [x] 5.1 Implement config loading for model ID, `max_tokens` (16000), timeout, `max_retries` and the price table with `verified_on` per model (Opus 5, Sonnet 5, Haiku 4.5, cache multipliers); verify with tests that every entry exposes its date and that a missing file or field fails loudly
- [x] 5.2 Implement cost computation from a usage object; verify with tests: 5,000 in / 2,000 out at $2/$10 gives $0.03, cache read and cache creation tokens use their multipliers, and an unknown model raises a configuration error

## 6. Model client

- [x] 6.1 Define the narrow SDK protocol and a fake implementation for tests, plus `CallRecord` and `CallFailure` (`truncated`, `refused`, `invalid_output`, `api_error`); verify the fake can script responses with a given stop reason, usage and parsed output in a test
- [x] 6.2 Implement the async structured call (D9 request path: `messages.create` with `output_config` from `transform_schema`, validation after the stop-reason check): request built from system prompt, content blocks and output model; latency measured around the call; record populated from usage and cost. Verify with fake-client tests: successful call populates every metric, two calls give independent records, two concurrent calls on one client both succeed, and the output model is generic (a non-invoice model works)
- [x] 6.3 Implement stop-reason handling before reading the parsed output; verify with fake-client tests that `max_tokens` yields `truncated` and `refusal` yields `refused`, both with tokens and cost recorded and no exception
- [x] 6.4 Implement error mapping: validation error to `invalid_output`, exhausted retryable errors and 400 to `api_error`, 401/403/404 raised, unknown model rejected before sending; `AsyncAnthropic` built with configured `max_retries` and `timeout`. Verify with fake-client tests for each case, and with an `httpx.MockTransport` test that repeated 529s stop at the retry ceiling

## 7. Prompt and extraction

- [x] 7.1 Write `prompts/extract_invoice/v1.md` (role, task, fail rather than guess for unsupported documents and invisible mandatory values; no examples) and a loader by version; verify with tests that `v1` loads and a missing version raises before any client call
- [x] 7.2 Implement single-document extraction: reject non-PDF input before calling, build a base64 PDF document block, prompt in system and only the document in the user turn, return the call record plus prompt version. Verify with fake-client tests for message layout, non-PDF rejection with zero calls, and the recorded fixture from 4.5 flowing through as an extracted outcome
- [x] 7.3 Implement the entry point (`python -m invoice_extractor.extract_one <pdf> [--max-tokens N]`) that prints model, tokens in/out, cache tokens, stop reason, latency, cost and outcome; verify with a fake-client test that a truncated record prints a summary and exits non-zero without a traceback

## 8. Manual acceptance (real API; not part of pytest)

- [ ] 8.1 Run the entry point on the spike Factura A; verify the outcome is extracted and total, issuer CUIT, customer CUIT, point of sale, invoice number and CAE match the PDF
- [ ] 8.2 Run it on the nota de crédito from 3.3; verify the outcome is a failure with `unsupported_document_type`
- [ ] 8.3 Run it on a one-page non-invoice PDF; verify the outcome is a failure with a reason, not an invoice
- [ ] 8.4 Run it on the spike with `--max-tokens 64`; verify a `truncated` call failure is printed with tokens and cost and no traceback
- [ ] 8.5 Replace the ESTIMATED table in design.md with the measured tokens, cost and latency from 8.1–8.4, labelled with date and model

## 9. Documentation follow-ups

- [x] 9.1 Update PRD 01: field table and R1.2 optional list per D1–D5, strike the nesting-risk ambiguity per D6; verify the PRD table matches the implemented schema field by field
- [x] 9.2 Update PRD 02: mark OQ-2.1 resolved as (a), add notas de crédito/débito to the R2 negatives table with their own tag, add the `currency` ARS convention as an explicit exception in R3.1; verify by review against design D1 and D4
- [x] 9.3 Update PRD 04: V3 with the WSFE formula (`net + non_taxed + exempt + vat + other_taxes = total`), new V2b line arithmetic check, and a note that V4's base per rate comes from items grouped by `vat_rate`; verify by review against design D2 and D3
- [x] 9.4 Add to PRD 03 open questions the list-scoring rule for `vat_breakdown` and `other_taxes` (must enter the measurement change log before the baseline); verify the question appears there and in design.md Open Questions
- [ ] 9.5 Run `pytest` with no API key and `git status` to confirm no `.env`, API key or generated PDF is committed
