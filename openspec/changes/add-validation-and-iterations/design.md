## Context

See proposal.md for motivation. Current state that shapes the approach:

- `ModelClient.call(system, content, output_model)` sends one user turn. A corrective attempt needs the previous output as an assistant turn and the problems as a second user turn, so the client has to widen.
- Transport retries happen inside the SDK (`max_retries` from `config/extractor.toml`), and their count is invisible to the caller. PRD 04 R2.4 wants it in the run record.
- `evaluation/execute.py` scores one `ExtractionRecord` per document, with `attempts=1` hard-coded (PRD 03 R4.3). `DocumentResult.extraction` is a single record, and `read_run_record` recomputes aggregates and rejects a record whose aggregates differ.
- The stage 3 baseline is near the ceiling: 30/30 correct outcomes and 3 wrong fields, all on B05 (`items[].vat_rate` `"0"` instead of `null`). The noise floor at n=30 is about ±9 points for one run and about ±12.6 between runs. Most iterations will be within noise, and the log has to say so.
- Measured baseline cost: $0.0376/doc and p95 44.4s (Sonnet 5, path A). Every estimate below starts from these numbers.
- Prerequisite: the B/C generator fix (see proposal) re-renders 15 documents and re-runs v1. The design assumes that after the fix, B/C items sum to the printed total and E already does.

## Goals / Non-Goals

**Goals:**
- A validator that is a pure function of `(Invoice, reference_date)` and passes every in-domain ground truth.
- One processing function that both the evaluation and `extract_one` call, so the CLI and the UI of later stages inherit validation and retries.
- Run records that can answer "how much did retries cost, and what did they fix" from disk alone.

**Non-Goals:**
- Batch API (R5.2) and prompt caching (R5.3). The run record will show whether the repeated document prefix in corrective attempts is worth caching, but enabling it is a later lever.
- The R6 schema levers (contained taxes, optional `unit_price`). The real set's "IVA Contenido" tickets will fail V3/V5, and that is reported, not fixed.
- A human review queue (PRD 05 R6).

## Decisions

### D1. Validation module: `validation.py`, one function per check

`validate(invoice: Invoice, *, today: date) -> list[Problem]`, where `Problem` is a frozen Pydantic model with `check: Literal["V1", ..., "V7"]`, `path: str` (same dotted/indexed paths as `compare.py`, for example `items[2].line_amount`), `message: str`, `expected: str | None` and `found: str | None`. Each check is a private function that returns its own problems, and `validate` concatenates them in check order, so the output is deterministic.

The module imports only `schema.py`. A test asserts that it imports nothing from `client`, `prompts`, `extraction` or `anthropic` (CC-2).

Tolerance (OQ-4.1): `Decimal("0.01") * n`, where n is the number of independently rounded amounts summed: items for V2, the item count at that rate for V4, the non-absent terms for V3, and 1 for V2b. Exact `Decimal` arithmetic, never float.

V3 has two forms. When `net_amount` is printed (Factura A), the check uses the WSFE formula. When it is not printed (B, C, E), the check is items + other taxes = total. The second form depends on the generator fix, and the spec scenario "Invoice without a printed net" pins it.

V5 rules come from the fiscal rules in the PRD plus what the dataset prints. A Factura B may carry item VAT rates (B03, B06 print an IVA column), so there is no "B has null vat_rate" rule, and failure-analysis hypothesis 2 is dropped (see Risks). The document-code-to-letter map (01/06/11/19) is an added redundancy, and it is cheap.

Alternatives: a rules engine or a list of declarative rules. Rejected: seven checks read better as seven functions, each with its own tests.

### D2. Processing pipeline: `processing.py`

```
process_document(path, *, client, prompt, correction_prompt, today, max_attempts, validate_on) -> ProcessedDocument
```

Loop, with at most `max_attempts` calls:
1. Call the model with the conversation so far: a document block for the first turn; after that, the growing history.
2. Branch on the call outcome:
   - `Parsed(Failed)`: final outcome is the model failure. Stop.
   - `Parsed(Extracted)`: validate. No problems (or validation off): accepted. Stop. Problems: they become the next turn's input.
   - `CallFailure(invalid_output)`: its Pydantic errors become problems, with `check="schema"`. Next turn.
   - `CallFailure(truncated | refused | api_error)`: final outcome is that failure. Stop. No corrective attempt: resending the same request would not change truncation at 16k tokens or a refusal, and transport errors were already retried.
3. The cap is reached with problems left: final outcome is `ValidationFailed(problems, last_invoice)`. The invoice is kept for human review and never counted as an extraction.

`ProcessedDocument` holds `attempts: list[Attempt]` (each attempt is a `CallRecord` plus that attempt's problems), `final: Accepted | ModelFailed | ValidationFailed | CallFailed`, and summed `cost_usd` and `latency_ms`.

The corrective turn is: user turn 1 (document block plus the unchanged extraction prompt as system), then an assistant turn with the previous raw JSON text, then user turn 2 rendered from `prompts/correct_invoice/v1.md` with the problem list. When the previous attempt was `invalid_output`, the assistant turn is the raw text that failed validation. It must come from the response, so `CallFailure` gains an optional `raw_text` field.

Every attempt resends the document, so it pays the document's input tokens again. That is the known cost of this design (see D6), and it is measured, not hidden.

`max_attempts` is validated as `1 <= n <= 5`. The upper bound keeps a misconfiguration from spending without limit.

Alternatives: (a) sending only the problems and the previous JSON, without the document. Rejected: the model cannot fix a misread without seeing the page again. (b) Placing the retry loop inside `ModelClient`. Rejected: the client is generic and knows nothing about validation (CC-2).

### D3. Client: conversation input and per-call transport count

`call(system, content | messages, output_model, max_tokens)`. `content: list[block]` keeps working and means one user turn. `messages: list[{"role", "content"}]` must alternate roles and start and end with `user`; anything else raises `ValueError` before sending.

Transport count: `from_config` builds the SDK with an `http_client` whose `request` event hook increments a `ContextVar[list[int] | None]`. `call` sets a fresh counter in its own task context before calling `messages.create` and reads it afterwards. Concurrent calls run in separate asyncio tasks, so each one sees its own counter (spec scenario "Concurrent calls count independently"). `CallRecord.transport_requests: int`, defaulting to 1 for records read from disk. With no hook installed (a fake SDK in tests), the counter stays at 0 and is reported as 1. Tests of the count use the existing `MockTransport` pattern in `tests/test_client.py`.

Alternative: disable SDK retries and write our own backoff loop. Rejected: it duplicates retry-after handling the SDK already does correctly, just to count.

### D4. Run record format v2, readable v1

`DocumentResult` gets `attempts: list[Attempt]`, `final_kind`, `transport_requests` and `format_version: 2`. The v1 `extraction` field is migrated in a `model_validator(mode="before")`: `extraction` becomes one attempt with no problems, and validation is marked off. `RunConfig` gets `correction_prompt_version: str | None`, `validation: bool`, `max_attempts: int` and `measurement_rules_version`. On v1 meta, missing fields default to `None`/`False`/`1`. `Aggregates` gets `validation_failures_by_check`, `documents_retried`, `validation_rejections` and `transport_retries`, all defaulting to empty or 0. So recomputing aggregates for a v1 record still equals the stored ones, and the consistency check in `read_run_record` keeps working unchanged.

A test loads the committed `runs/20260922-155901-path_a-148bac7` and asserts that the report renders byte-identical to what it renders before the change (spec "Stage 3 run record still readable").

`compare()` receives the final accepted `ExtractionResult` or `None`. For `ValidationFailed` it receives `None`, which the measurement rules already classify as `explicit_failure` (§1 names "validation still failing after the last attempt"). No change to `measurement-rules.md`.

Run ID becomes `{ts}-{model_short}-{prompt}-path_{p}-{sha}`, for example `20260925-101500-sonnet5-v2-path_a-abc1234`. Old IDs are read as-is; nothing parses them.

### D5. Version comparison and iteration log

`evaluation/version_comparison.py` compares two complete run records. It refuses when their manifest document IDs or `measurement_rules_version` differ, then reuses `stats.mcnemar_exact`, `report.field_precision` and the Wilson `rate`. `path_comparison.py` stays as it is. Its coverage logic is specific to path B and not worth generalizing.

Versions are registered in `docs/iterations/versions.toml`, with `version`, `lever`, `compares_to`, `run_id`, `hypothesis_file` and `change`. Each hypothesis is written in `docs/iterations/vN.md` and committed before running (R3.2). `python -m invoice_extractor.iterations` renders the log table (spec columns) and the model comparison table from the registry and the run records, and rewrites the README between `<!-- iteration-log:start -->` and `<!-- iteration-log:end -->` markers. `--check` exits non-zero when the README is stale. The README is a skeleton in this stage: title, one-line problem, the log section. PRD 05 writes the rest around it.

Planned versions (all path A and the full dataset; each changes one lever):

| Version | Lever | Compares to | Hypothesis source |
|---|---|---|---|
| v1 | baseline (re-run after the generator fix) | — | — |
| v2 | validation on + corrective retries, cap 3 | v1 | PRD 04 R1/R2; expected: same accuracy, catches synthetic corruptions only, measures retry cost |
| v3 | prompt `extract_invoice/v2`: an absent IVA column means `vat_rate` null, not "0" | v2 | failure-analysis hypothesis 1 (B05) |
| v4 | model `claude-haiku-4-5` | best of v2/v3 | R5.1: cost down |
| v5 | model `claude-opus-5` | best of v2/v3 | R5.1: quality ceiling vs cost |

Hypothesis 3 (dense tables) is re-checked in the per-tag breakdown of every run. It gets no version of its own unless the evidence appears.

### D6. Model call sites, failure handling and cost

There is one call site, `ModelClient.call`, reached from `processing.process_document`. Every model call goes through it (the evaluation, `extract_one`, both ingestion paths):

| Failure | Handling |
|---|---|
| API error (4xx other than auth/permission/not-found, 5xx after retries, connection) | SDK retries with capped backoff; then `api_error` record; document ends `CallFailed`; run continues |
| Timeout | SDK timeout (`timeout_seconds`) → retried as transport → `api_error` |
| Rate limit / overload (429/529) | SDK retries honoring retry-after up to `max_retries`; count recorded (D3) |
| Truncated (`max_tokens`, context window) | `truncated` failure, no corrective attempt |
| Refused | `refused` failure, no corrective attempt |
| Invalid output (client-side schema) | `invalid_output` → corrective attempt with the errors (R2.3) |
| Auth / permission / unknown model | raised; the run aborts (every later call would fail the same way) |

Estimated cost and latency (**estimated until measured**; baseline Sonnet 5 = $0.0376/doc, p95 44.4s):

| Run | Tokens per call (est.) | Cost/doc (est.) | Run cost (est.) | p95 (est.) |
|---|---|---|---|---|
| v2 Sonnet + retries | first call as baseline; a corrective call adds ~2–3k input (previous JSON + problems) | $0.038–0.045 (≤10% of docs retried) | ~$1.3 | ~45s; retried docs ~2× |
| v3 Sonnet, prompt v2 | +~100 input tokens | ~$0.038 | ~$1.2 | ~45s |
| v4 Haiku 4.5 | same input; less output (no adaptive thinking by default) | ~$0.010–0.020 | ~$0.5 | ~15–25s |
| v5 Opus 5 | same input; thinking output likely higher | ~$0.10–0.15 | ~$3–4.5 | ~60–90s |

That is about $6–7.5 in total, inside the USD 10 budget, with room for one re-run. Per-run spend caps: $3 for Sonnet and Haiku runs, $6 for Opus. The generator-fix baseline re-run is budgeted by its own change.

### D7. Corrupted-invoice tests

Tests take each ground-truth invoice, apply one targeted corruption per check (flip a CUIT digit, drop an item, change the total by 1.00, swap letter B→A, set CAE expiry before issue, cut the CAE to 13 digits), and assert exactly that check fires on exactly that path. The same fixtures drive the pipeline tests: a fake SDK that returns the corrupted invoice first and the clean one second (success on attempt 2), or the corrupted one every time (cap). This covers PRD 04 R1.1 and PRD 05 R2.1/R2.4 in one place.

## Risks / Trade-offs

- [Validator false rejections turn correct extractions into failures] → The spec requirement "No false rejections on ground truth" is a test over all 25 in-domain invoices, and false rejections stay a headline line of every report.
- [Retries hide a weak prompt and multiply cost] → The report shows retry rate with its interval and flags ≥30%. Cost per doc includes every attempt.
- [The corrective turn nudges the model to "make the numbers add up" by inventing values] → The corrective prompt says to fail rather than adjust a value that is not printed. Invented values are compared v1 vs v2 in the paired comparison, and an increase is a logged regression.
- [Iterations sit inside the noise floor] → Every row carries McNemar p and a "within noise" statement. The log's value is honest measurement, not a rising number.
- [Failure-analysis hypothesis 2 was wrong] → Recorded here and in `docs/iterations/v2.md`: B03/B06 legitimately print item VAT rates on a Factura B, so the proposed check would have rejected 2 correct documents. B05 goes to the prompt lever (v3).
- [Real "IVA Contenido" tickets fail V3/V5] → Real-set section only, never a headline number. The first R6 lever is next in line.
- [ContextVar counting breaks if the SDK moves requests to another task] → A test with two concurrent calls and one 529 pins the behavior. If it breaks on an SDK bump, the field falls back to "unknown" (None) rather than a wrong number.

## Migration Plan

- Order: the generator-fix change is archived first → new v1 run committed → this change.
- Run records written before this change stay readable (D4). Nothing on disk is rewritten.
- `extract_one` output gains an attempts line and, on validation failure, the problem list. Its exit codes are unchanged.
