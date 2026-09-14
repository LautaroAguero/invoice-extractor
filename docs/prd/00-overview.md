# PRD 00 · Overview: invoice-extractor

Status: draft · Last updated: 2026-09-14

This is the umbrella document for the five stage PRDs. Each stage PRD says **what** has to exist and **how we know it is done**. The **how** (module layout, function signatures, prompt wording) belongs in the OpenSpec proposal and design for that stage.

## Problem

Accounting and back-office teams re-type data from Argentine invoices (facturas A, B, C, E) into their systems by hand. The work is slow and expensive, and its errors propagate silently into ledgers and tax filings.

## Goal

A system that takes invoice documents and returns validated, structured objects. It also **measures its own reliability and its own cost per document**. The measurement is the product: an extractor with no measured precision and cost per document is not finished.

## Non-goals

- Production deployment, multi-tenant APIs, UIs.
- Real invoices. The dataset is 100% synthetic (see Decisions).
- Training or fine-tuning models.
- Integration with ARCA/AFIP web services (no CAE validation against the real registry).

## Stages

| # | PRD | Outcome | Course estimate |
|---|---|---|---|
| 1 | [Happy path](01-happy-path.md) | One document → one validated object via native structured outputs | ~2 h |
| 2 | [Dataset](02-dataset.md) | ≥30 synthetic documents with ground truth, ≥8 hard cases | ~3 h |
| 3 | [Measure and discover](03-measure-and-discover.md) | One command produces the quality report; worst field identified | ~2 h |
| 4 | [Iterate with evidence](04-iterate-with-evidence.md) | Business validation, corrective retries, logged iterations with numbers | ~3 h |
| 5 | [Finish](05-finish.md) | CLI, API-free tests, README, error handling | ~2 h |

Stages are ordered on purpose. **Nothing gets "improved" before stage 3 can measure it.**

## Decisions already made

| Decision | Choice | Why | Revisit if |
|---|---|---|---|
| Domain | Argentine invoices (A, B, C, E) | Rich redundancies that can be checked deterministically: CUIT check digit, VAT rules per invoice type, items → net → VAT → total, CAE | — |
| Data source | 100% synthetic, rendered with pyafipws `pyfepdf` | Ground truth by construction, publishable, no personal data | Headline precision is needed on real invoices |
| Repo language | English (code, schema, prompts, docs). Fiscal terms stay in Spanish inside field descriptions (CUIT, CAE, Responsable Inscripto) | Broad audience; the model must match the literal strings printed on the document | — |
| Structured output level | Native structured outputs (`messages.parse` with a Pydantic model) | Level 3 in course chapter 5: shape guaranteed by the API | — |
| Generator isolation | `tools/generate_invoices/` has its own venv and requirements and is never imported by the extractor | pyafipws is GPL-3.0 and needs compatibility patches on Python 3.14 | — |
| Provider SDK | Official `anthropic` Python SDK | — | Provider comparison becomes a goal |

## Cross-cutting requirements (apply to every stage)

- **CC-1 Typed contracts.** Every model input and output crosses the boundary as a Pydantic model. No bare dicts.
- **CC-2 Separation.** Extraction code knows nothing about business rules, and validation code knows nothing about the model. Switching provider touches one module; changing business rules touches another.
- **CC-3 Instrumented calls.** Every model call records model ID, input/output/cache tokens, stop reason, latency and cost in USD. Cost is computed from `usage`, never estimated after the fact.
- **CC-4 Failure-aware calls.** Every call site handles API errors, timeouts, rate limits/overload, and malformed or truncated output (`stop_reason` of `max_tokens` or `refusal`). Transport retries use exponential backoff with a ceiling.
- **CC-5 Bounded spend.** Each command that calls the model has a spend cap per run and an attempt cap per document. Neither can be unlimited.
- **CC-6 Versioned prompts.** Prompts live in `prompts/extract_invoice/vN.md`, never inline in code.
- **CC-7 No secrets or personal data in the repo.** `.env` is ignored and `.env.example` is committed. Synthetic identifiers only.
- **CC-8 Tests never hit the API.** `pytest` passes with no API key configured.

## Verified platform facts (as of 2026-09-14; re-verify before relying on them)

- Native structured outputs are supported on `claude-opus-5`, `claude-sonnet-5` and `claude-haiku-4-5`. On `messages.create` the parameter is `output_config={"format": ...}`; `output_format=` is only the `messages.parse()` helper argument.
- Unsupported JSON Schema features: numeric constraints (`minimum`, `maximum`), string length constraints, recursive schemas. The Python SDK strips them from the schema and validates them client-side, so `parse()` can still raise a validation error.
- Citations cannot be combined with structured outputs (the request returns 400). Source quotes, if wanted, must be schema fields.
- PDF input: 32 MB per request; 600 pages, or 100 when the request's context window is under 1M tokens (Haiku 4.5 has 200K). Each page costs roughly 1,500–3,000 text tokens plus the page image.
- List prices, USD per million input/output tokens: Opus 5 $5/$25, Sonnet 5 $2/$10, Haiku 4.5 $1/$5. Batch API is 50% off.
- Opus 5 runs adaptive thinking by default, and thinking tokens are billed as output.

## Known statistical constraint

With n=30, one run's pass rate has a noise floor of about ±8.9 points (95%). Between two independent runs, differences below about ±12.6 points cannot be told apart from noise (`/eval-stats`). Consequences for every stage:

- Comparisons are **paired** (same documents, McNemar).
- Per-field precision is the main signal, not only the per-document rate.
- Every reported rate carries its n and interval.

## Open questions (blocking)

- **OQ-1 Measurement rules.** Blocks the ground truth format in PRD 02 and the report in PRD 03. See PRD 03 § Open questions.
