"""Run a dataset through the extractor with bounded concurrency and a spend cap (PRD 03 R4, design D8).

This module orchestrates; it does not call the model itself. Each document goes through an
ingestion-path extractor, which uses `ModelClient.call` and so inherits its failure handling: API
errors, truncation, refusal and invalid output come back as typed failures and become that
document's outcome (R4.3). Only configuration errors (authentication, permission, unknown model)
are raised by the client, because every later call would fail the same way; they abort the run.
"""

import asyncio
from decimal import Decimal

from invoice_extractor.client import ModelClient, Parsed
from invoice_extractor.evaluation.compare import compare
from invoice_extractor.evaluation.ingestion import EXTRACTORS, NoCall
from invoice_extractor.evaluation.manifest import DocumentEntry, Manifest
from invoice_extractor.evaluation.run_record import (
    DocumentResult,
    IngestionPath,
    RunRecord,
    aggregate,
    build_run_config,
)
from invoice_extractor.extraction import ExtractionRecord
from invoice_extractor.prompts import Prompt
from invoice_extractor.schema import Extracted


def _score(manifest: Manifest, entry: DocumentEntry, outcome: ExtractionRecord | NoCall) -> DocumentResult:
    truth = manifest.load_ground_truth(entry).result
    truth_invoice = truth.invoice if isinstance(truth, Extracted) else None
    if isinstance(outcome, NoCall):
        return DocumentResult(
            entry=entry,
            extraction=None,
            no_call_reason=outcome.reason,
            attempts=0,
            comparison=compare(None, truth_invoice, entry.expected_outcome, entry.expected_reason),
        )
    call_outcome = outcome.call.outcome
    prediction = call_outcome.value if isinstance(call_outcome, Parsed) else None
    return DocumentResult(
        entry=entry,
        extraction=outcome,
        no_call_reason=None,
        attempts=1,  # one attempt per document in this stage (PRD 03 R4.3)
        comparison=compare(prediction, truth_invoice, entry.expected_outcome, entry.expected_reason),
    )


async def execute(
    manifest: Manifest,
    client: ModelClient,
    prompt: Prompt,
    *,
    ingestion_path: IngestionPath = "a",
    max_concurrency: int,
    spend_cap_usd: Decimal,
) -> RunRecord:
    """Extract and score every document of `manifest`.

    At most `max_concurrency` documents are in flight. Once the running cost reaches
    `spend_cap_usd` no new document is started; calls already in flight finish and are recorded,
    so the total can exceed the cap by at most the cost of those calls. A run cut short that way
    is marked `complete=False` and holds only the documents that were started.
    """
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be at least 1")
    if spend_cap_usd <= 0:
        raise ValueError("spend_cap_usd must be positive: nothing may run without a spend limit")
    try:
        extractor = EXTRACTORS[ingestion_path]
    except KeyError:
        raise ValueError(f"ingestion path {ingestion_path!r} is not available") from None

    slots = asyncio.Semaphore(max_concurrency)
    spent = Decimal(0)
    stopped_by_cap = False

    async def run_one(entry: DocumentEntry) -> DocumentResult | None:
        nonlocal spent, stopped_by_cap
        async with slots:
            # `spent` holds only completed calls; calls in flight are not counted until they finish.
            if spent >= spend_cap_usd:
                stopped_by_cap = True
                return None
            outcome = await extractor(entry, manifest.document_path(entry), client, prompt)
            result = _score(manifest, entry, outcome)
            spent += result.cost_usd
            return result

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(run_one(entry)) for entry in manifest.entries]
    except ExceptionGroup as failure:
        # A configuration error or a broken dataset: not a document outcome, so the run does not continue.
        raise failure.exceptions[0] from None

    results = [result for task in tasks if (result := task.result()) is not None]
    config = build_run_config(
        model_id=client.model,
        prompt_version=prompt.version,
        ingestion_path=ingestion_path,
        generator_version=manifest.generator_version,
        max_concurrency=max_concurrency,
        spend_cap_usd=spend_cap_usd,
        complete=not stopped_by_cap,
    )
    return RunRecord(config=config, aggregates=aggregate(results), results=results)
