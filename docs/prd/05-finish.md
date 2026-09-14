# PRD 05 · Finish

Status: draft · Stage 5 of 5 · Depends on: PRD 01–04 · Course estimate: ~2 h

## Why

Whoever evaluates this portfolio will spend about two minutes on it. The system has to run on a clean machine from the README alone, its tests must pass without spending money, and the README has to show the results and the design judgement above the fold. This stage turns a working experiment into something another engineer can run, verify and trust.

## Scope

**In**
- A command-line interface with three commands: process one document, batch a folder, evaluate a dataset.
- Test suite that runs without an API key.
- Error handling review against the four failure modes.
- The README, written as the main deliverable.
- Repository hygiene: license, `.env.example`, secrets and personal data check.
- Optional: human review queue.

**Out**
- FastAPI service (optional in the course; not planned).
- Deployment, containers, CI beyond running the tests (CI is a nice-to-have, not a requirement).

## Requirements

### R1 · CLI

```bash
invoice-extractor process invoice.pdf --output json
invoice-extractor batch ./documents/ --output results.jsonl
invoice-extractor evaluate --dataset ./ground_truth/ --report report.md
```

- **R1.1** `process` prints the validated invoice, or an explicit failure with its reason, plus attempts, cost and latency. The exit code differs between success, explicit failure and error.
- **R1.2** `batch` writes one JSON line per document with outcome, data or failure, attempts, cost and latency. A failing document does not stop the batch, and a summary line closes the run.
- **R1.3** `evaluate` produces the PRD 03 report and saves the run record. A separate flag or subcommand re-renders a report from a saved run record without network access.
- **R1.4** Model, attempt cap and spend cap are configurable through flags or environment variables, with safe defaults. The spend cap cannot be disabled.
- **R1.5** Input formats: PDF (with or without a text layer) and JPG/PNG. Any other format fails with a clear message before calling the model.
- **R1.6** A missing API key fails fast with an actionable message; it never crashes with a stack trace.

### R2 · Tests without API

`pytest` passes on a machine with no API key and no network access. Coverage must include:

- **R2.1** Business validation: every check, including corrupted invoices.
- **R2.2** Comparison and normalization (PRD 03 R2), including the OQ-1 rules.
- **R2.3** Cost calculation from recorded `usage`, including cache tokens.
- **R2.4** Retry logic with a fake client: success on attempt 2, permanent failure hitting the cap, previous errors present in the next request.
- **R2.5** Failure handling with a fake client: truncated (`max_tokens`), refusal, API error, timeout, rate limit.
- **R2.6** Spend cap: a run stops and is marked incomplete.
- **R2.7** Report rendering from a fixture run record.
- **R2.8** No test asserts on exact model text. Recorded responses are fixtures, never live calls.

### R3 · Error handling review

Every model call site is checked against the four failure modes (API error, timeout, rate limit or overload, malformed or truncated output). Each one either maps to a typed outcome or is retried within a cap. The review result goes in a short section of the design docs.

### R4 · README (the real deliverable)

In this order:

1. **Problem**, in two sentences, in business terms.
2. **Demo**: three terminal lines with input and output, or a GIF.
3. **Results**, visible without scrolling: final precision with n and interval, worst field, invented values, cost/doc and p95; plus the model comparison table if PRD 04 R5.1 was done.
4. **How it works**: a simple pipeline diagram (ingest → extract → validate → retry or fail → result).
5. **Design decisions**: 3–4 paragraphs covering why native structured outputs, why validation is separate from extraction, which ingestion path won and at what cost, and why the dataset is synthetic.
6. **Iteration log** (PRD 04 R4).
7. **Known limitations**, including at least: 100% synthetic dataset, so precision on real invoices is not measured; n=30 noise floor; no ARCA registry validation of CUIT or CAE.
8. **How to run it**: install, `.env` setup, the three commands, how to run the tests, how to regenerate the dataset (the generator's separate venv and its GPL notice).

A Spanish `README.es.md` is optional and only worth it if kept in sync.

### R5 · Repository hygiene

- **R5.1** `LICENSE` for the extractor, plus a notice that `tools/generate_invoices/` (template CSV, `afip.png`, generator code) is GPL-3.0.
- **R5.2** `.env.example` with variable names only, and `.env` git-ignored.
- **R5.3** A scan of the repo and its history for credentials and non-synthetic personal data before the first push.
- **R5.4** A dependency manifest (`pyproject.toml`) with pinned or bounded versions for the extractor.

### R6 · Optional: human review queue

Documents that end in an explicit failure after validation go to a separate `review.jsonl`, carrying the problems, the last extraction and the document path, so a human can resolve them. Measure how many documents a run sends to review.

## Acceptance criteria (course, mapped)

- [ ] Runs on a clean machine following only the README (verified in a fresh clone and a fresh venv).
- [ ] `pytest` passes with no API key configured.
- [ ] The evaluation report is generated with one command.
- [ ] Per-field precision is measured, not estimated.
- [ ] Cost per document is measured, not estimated.
- [ ] A document that is not an invoice produces an explicit failure, not invented data.
- [ ] Retries have a cap and cannot spend without limit.
- [ ] No keys or personal data in the repository.
- [ ] The README has the iteration log with numbers.

## Risks

| Risk | Mitigation |
|---|---|
| "Works on my machine" (Windows paths, the Python 3.14-only generator patches) | Clean-clone verification; document the generator's separate setup explicitly |
| README numbers drift from the committed run records | README numbers come from run records; re-render before publishing |
| Tests silently hit the API | Tests run with the key unset; the client refuses to construct without an explicit key, so tests must inject a fake client |

## Open questions

- **OQ-5.1** License for the extractor itself (MIT, Apache-2.0, or GPL-3.0 for simplicity alongside the generator)?
- **OQ-5.2** CLI framework: Typer or argparse? Typer adds a dependency; argparse is enough for three commands.
