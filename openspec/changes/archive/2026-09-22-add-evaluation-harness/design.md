## Context

Stage 1 (`add-happy-path-extraction`) gives us `ModelClient.call()` (returns a `CallRecord` with tokens/cost/latency/outcome, PDF-only content) and `extract_document()` (PDF path → `ExtractionRecord`). Stage 2 (`add-synthetic-dataset`) gives us `ground_truth/` (30 docs + `manifest.jsonl` with `expected_outcome`, `expected_reason`, `tags`, `format`) and `ground_truth_real/` (2 docs, git-ignored). `docs/measurement-rules.md` is fixed and committed. There is no evaluation code yet, no `scipy`, no `pdfplumber`, and `runs/` does not exist. See proposal.md - Why for motivation and requirement IDs.

## Goals / Non-Goals

**Goals:**
- One place that runs the dataset, scores it, and persists everything needed to reproduce the report without another model call.
- Keep `evaluate` (spends money) and `report` (reads a file) as separate, independently testable operations (R1.2).
- Reuse stage 1's instrumentation (`CallRecord`) instead of re-deriving cost/tokens.

**Non-Goals:**
- Fixing what the analysis finds, or business validation (PRD 04).
- CLI polish — a minimal `argparse` entry point is enough here (PRD 05 does the rest).
- OCR for path B, or any change to what path A sends for PDFs.

## Decisions

### D1. Module layout: `src/invoice_extractor/evaluation/`

```
evaluation/
  manifest.py     # load ground_truth/manifest.jsonl and ground_truth_real/manifest.jsonl into a typed Manifest/DocumentEntry
  compare.py       # docs/measurement-rules.md §2-§4: normalize, compare one field, compare one Invoice, classify document outcome
  stats.py          # wilson_interval(k, n), mcnemar_exact(b, c) — no scipy dependency
  run_record.py    # RunConfig, DocumentResult, RunRecord (pydantic), read/write to runs/
  execute.py        # run the dataset: bounded concurrency (asyncio.Semaphore) + spend cap, builds a RunRecord
  report.py          # RunRecord -> report sections -> terminal text + markdown (pure, R1.2)
  ingestion.py        # path B: pdfplumber text extraction, path A/B dispatch for the comparison
  path_comparison.py   # R5: run both paths, pair them, render the comparison table
evaluate.py    # entry point: python -m invoice_extractor.evaluate (writes a run record)
report_cli.py  # entry point: python -m invoice_extractor.report_cli <run-record> (re-renders, no network)
```

Alternative considered: fold everything into `extraction.py` / a single `evaluation.py`. Rejected — `compare.py`, `stats.py` and `report.py` have zero dependency on the model client and are the most test-heavy part of this stage; keeping them in their own files makes that visible and matches the existing one-concern-per-module style (`client.py`, `config.py`, `extraction.py`, `prompts.py`, `schema.py`).

### D2. Run record shape: one JSON + one JSONL per run

`runs/<run_id>.json` — `RunConfig` (model ID, prompt version, schema hash, `anthropic`/`pydantic` versions, ingestion path, generator version from the manifest, git SHA via `git rev-parse HEAD`, timestamp, `complete: bool`) plus `aggregates` (computed once at write time, not re-derived by `report.py`, so a re-render can be diffed against them as a consistency check).
`runs/<run_id>.jsonl` — one line per document: `{document_id, extraction: ExtractionRecord, comparison: ComparisonResult}`.

`run_id` is `<timestamp>-<ingestion_path>-<short_git_sha>`, e.g. `20260917-1200-path_a-b8bc5d4`.

Real-set runs use the same shapes under `runs/real/` (git-ignored — `.gitignore` gets a `runs/real/` line, following the existing `ground_truth_real/` pattern). `execute.py` takes the manifest path and the output directory as separate parameters, so nothing about "which set this is" is inferred from content; the caller (the CLI entry point) decides the directory, which is what keeps a real-set run from ever landing in the committed `runs/`.

Alternative considered: a single JSON with a `documents` array. Rejected for two reasons: JSONL diffs cleanly per document in git (synthetic run records are committed, R1.3), and `report.py` can stream it instead of holding the whole run in memory — not a real concern at n=32, but it matches how `manifest.jsonl` already works in this repo.

### D3. Comparison: reflect over the `Invoice` model

`compare.py` walks `Invoice`'s Pydantic fields (`model_fields`) rather than hardcoding each field name. Leaf scalar fields go through one normalize-and-equal function keyed by a small type table (Decimal, date, "digits", "casefold-text", enum) built once from field metadata (annotation type + which fields are the digit-only ones per §4 — `cuit`, `point_of_sale`, `invoice_number`, CAE `number`). `items`, `vat_breakdown`, `other_taxes` get the shared position-matching routine from §3, parameterized by which sub-model they hold.

Alternative considered: a hand-written comparison function per field (30+ `if` branches). Rejected — measurement-rules.md's normalization table already collapses to 6 kinds (D4 below), and hardcoding each field name would mean this module silently drifts from `schema.py` the next time a field is added, instead of failing loudly (an unrecognized field/type in the table raises rather than being skipped).

### D4. Statistics: hand-rolled Wilson interval and McNemar exact, no `scipy`

Wilson score interval is a closed-form formula (~10 lines). McNemar exact (n=30, so `b+c` is always small) is a two-sided exact binomial test on the discordant pairs, also closed-form with `math.comb`. Both are unit-testable against known reference values (e.g. Wilson interval for k=27, n=30 against a published table).

Alternative considered: add `scipy` for `scipy.stats.binomtest` / a Wilson helper. Rejected — it would be the project's first heavy numeric dependency for two formulas the project already commits to in `docs/measurement-rules.md` §6, and hand-rolling keeps the trust chain (which exact test, which correction) visible in this repo instead of inside a library default.

### D5. `pdfplumber` as a normal dependency

Added to `[project.dependencies]` in `pyproject.toml`, imported directly by `evaluation/ingestion.py`. Unlike `tools/generate_invoices/pyafipws` (GPL-3.0, needs its own venv so its license never touches the extractor), `pdfplumber` is MIT and has no license interaction with this project's code — no isolation needed. This was decided at spike time (OQ-3.1 in PRD 03).

### D6. JPG support in `extraction.py`: image content block

`pdf_document_block` gets a sibling `image_block(path)` that base64-encodes the file and returns `{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": ...}}`. `extract_document` dispatches on suffix: `.pdf` → document block, `.jpg`/`.jpeg` → image block, anything else → `UnsupportedInputError`, unchanged from stage 1 except for the added branch. This is the same `client.call()` call site as stage 1 (see D7) — only the content block passed to it changes.

### D7. Model call sites and failure handling (unchanged from stage 1)

This change adds no new call site to the model. Both the per-document evaluation loop (path A) and the path-comparison run (path A and path B) call `extract_document()` / `client.call()` exactly as stage 1 does, so every failure mode (truncated, refused, invalid output, api_error, and the configuration errors that raise instead of returning a record) is handled exactly per `model-client` spec — nothing here changes that behavior. `execute.py`'s job is orchestration around that call: bounded concurrency and the spend cap (D8), not a new way of calling the model.

Path B (`pdfplumber` text) never calls the model itself — it produces the text content block that path A's document/image block is swapped for; the same `client.call()` is then used with `content=[{"type": "text", "text": extracted_text}]`.

**Measured** on the baseline run (2026-09-22, `claude-sonnet-5`, prompt v1, run `20260922-155901-path_a-148bac7` / `20260922-160125-path_b-148bac7`, 30 documents): path A cost $0.0376/doc mean ($1.1287 total), p50 latency 12.3s, p95 44.4s. Path B cost $0.0300/doc mean ($0.8992 total, over the 26 documents it attempted), p50 latency 13.5s, p95 42.1s. The original estimate (~$0.005-0.008/doc, 2-6s) undershot cost by roughly 5x — Sonnet 5's adaptive thinking on a page-image input costs more output tokens than the estimate assumed — and undershot latency similarly; both are now measured facts, not estimates, and PRD 04's iterations should budget against these figures, not the ones above.

### D8. Bounded concurrency and spend cap

`execute.py` uses an `asyncio.Semaphore(config.max_concurrency)` around each document's `extract_document()` call, and a single `asyncio.Lock`-protected running total compared against `config.spend_cap_usd` after every completed call. When the running total would exceed the cap, in-flight calls are allowed to finish (never cancelled mid-call, so their cost is still recorded) but no new call starts; the resulting `RunRecord` is written with `complete=False`. `report.py` refuses to render a report whose `complete` is `False` (R4.2, "nothing is reported as a full run").

### D9. What "worst field" means (PRD 03 R3.2)

The report marks the lowest-precision line among the scalar fields and the `<list>_per_entry` lines, ties broken by name. The `<list>_exact` lines are excluded: they are document-level composites of many fields, so one bad row anywhere makes them the lowest by construction and they would never say which field is weak. When every scored field is at 100% nothing is marked, so a tie-break never names a field that did not fail.

Alternative considered: include every printed line. Rejected for the reason above. Alternative considered: break list entries down into per-sub-field lines (`items[].unit_price`). Not done here because `docs/measurement-rules.md` §3 scores lists as `_exact` and `_per_entry` only; sub-field detail lives in each comparison's `entry_errors` and is what the failure analysis (PRD 03 R6) reads.

### D10. How the two paths are compared and the winner is named (PRD 03 R5.2-R5.4)

`compare_records(run_a, run_b)` is a pure function of two saved run records, so a comparison re-renders without the model; `compare_paths` only produces the two records (path A then path B, each with its own spend cap). Only synthetic documents take part, and both runs must be complete and cover the same documents.

- **Coverage group.** Documents path B ended without a call (no text layer, an image, or a PDF that cannot be parsed, which is recorded as that document's outcome instead of aborting the run) are listed apart and left out of the McNemar test. Including them would test "path B cannot read images", which is a coverage fact, not a difference in extraction quality (R5.3).
- **Paired test.** McNemar exact over per-document correct outcome on the documents both paths attempted. Field deltas (B minus A, in points) use only the documents both paths extracted, so every field has the same denominator on both sides.
- **Winner.** The path with more correct outcomes over all documents; a tie goes to the cheaper path per document. Coverage counts here, because reading every document is part of the domain. The trade-off sentence is built from the measured cost, p95 latency, coverage and McNemar p-value, and says "within the noise" when p >= 0.05, so a winner is never presented as statistically established when it is not.

Alternative considered: a hand-written verdict in a document. Rejected because it can drift from the numbers; the generated sentence is regenerated with them, and `docs/failure-analysis.md` adds the interpretation.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Hand-rolled Wilson/McNemar has a subtle formula bug | Unit tests against published reference values (design D4); code stays small and reviewable |
| Reflection-based comparison (D3) is harder to read than explicit field code | The type-table approach keeps per-field logic to one line each; an unmapped field raises instead of silently passing, so drift from `schema.py` is loud |
| Real-set output accidentally lands in a committed path | `execute.py` never infers the output directory; the CLI entry point that calls it for `ground_truth_real/` is the only place `runs/real/` is named, and it is covered by a test asserting the write path |
| `pdfplumber` extraction behaves differently across the dataset's mixed PDF sources (native + rendered) | R5.3 already carves out `skewed_scan`/`image_input` as a separate coverage group instead of averaging them into path B's precision |

## Open Questions

None — OQ-3.1 and OQ-3.2 were resolved before this design (see proposal.md), and every decision above was made here rather than deferred.
