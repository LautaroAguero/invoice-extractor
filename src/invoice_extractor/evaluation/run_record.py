"""Run records: what one evaluation run writes to disk (PRD 03 R1, design D2).

A run is two files sharing a `run_id`: `<run_id>.json` (config and aggregates) and
`<run_id>.jsonl` (one `DocumentResult` per line). Everything the report needs is in them, so a
report never has to call the model (R1.2).
"""

import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from importlib import metadata
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, ConfigDict, model_validator

from invoice_extractor.evaluation.compare import Classification, ComparisonResult
from invoice_extractor.evaluation.manifest import REPO_ROOT, DocumentEntry
from invoice_extractor.evaluation.stats import percentile
from invoice_extractor.extraction import ExtractionRecord
from invoice_extractor.schema import ExtractionResult

RUNS_DIR = REPO_ROOT / "runs"
REAL_RUNS_DIRNAME = "real"

IngestionPath = Literal["a", "b"]
# Why a document ended in an explicit failure without any model call (path B, PRD 03 R5.3).
NoCallReason = Literal["no_text_layer", "image_input", "unreadable_pdf"]

_CLASSIFICATIONS: tuple[Classification, ...] = (
    "extraction",
    "false_rejection",
    "false_acceptance",
    "correct_rejection",
)


class RunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    prompt_version: str
    # Hash of the schema actually sent (after `anthropic.transform_schema`), not of the Pydantic source.
    schema_hash: str
    anthropic_version: str
    pydantic_version: str
    ingestion_path: IngestionPath
    # Provenance of the rendered documents, from the manifest; None for the real set.
    generator_version: dict[str, str] | None
    git_sha: str | None
    # True when the tree had uncommitted changes, so the SHA alone does not identify the code that ran.
    git_dirty: bool | None
    timestamp: datetime
    max_concurrency: int
    spend_cap_usd: Decimal
    # False when the spend cap stopped the run: such a record is never reported as a result (R4.2).
    complete: bool


class DocumentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry: DocumentEntry
    # None when the document ended in an explicit failure without any model call.
    extraction: ExtractionRecord | None
    no_call_reason: NoCallReason | None
    # Corrective attempts (1 = no retry; PRD 03 R4.3 fixes it at 1). 0 when no call was made.
    attempts: int
    comparison: ComparisonResult

    @model_validator(mode="after")
    def _a_call_or_a_reason(self) -> "DocumentResult":
        if (self.extraction is None) == (self.no_call_reason is None):
            raise ValueError("a document has either an extraction record or a no_call_reason, never both or neither")
        return self

    @property
    def cost_usd(self) -> Decimal:
        return self.extraction.call.cost_usd if self.extraction else Decimal(0)

    @property
    def latency_ms(self) -> int | None:
        return self.extraction.call.latency_ms if self.extraction else None


class Aggregates(BaseModel):
    model_config = ConfigDict(frozen=True)

    documents: int
    classifications: dict[Classification, int]
    total_cost_usd: Decimal
    input_tokens: int
    output_tokens: int  # includes thinking tokens, as the API reports them
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    # Over documents that made a call; None when none did.
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    attempts: dict[int, int]


class RunRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    config: RunConfig
    aggregates: Aggregates
    results: list[DocumentResult]


class IncompleteRunError(ValueError):
    """The run record was cut short by the spend cap and cannot be reported as a result."""


def aggregate(results: list[DocumentResult]) -> Aggregates:
    calls = [r.extraction.call for r in results if r.extraction]
    latencies = [call.latency_ms for call in calls]
    counted = Counter(r.comparison.classification for r in results)
    return Aggregates(
        documents=len(results),
        classifications={name: counted[name] for name in _CLASSIFICATIONS},
        total_cost_usd=sum((call.cost_usd for call in calls), Decimal(0)),
        input_tokens=sum(call.input_tokens for call in calls),
        output_tokens=sum(call.output_tokens for call in calls),
        cache_read_input_tokens=sum(call.cache_read_input_tokens for call in calls),
        cache_creation_input_tokens=sum(call.cache_creation_input_tokens for call in calls),
        latency_p50_ms=int(percentile(latencies, 0.5)) if latencies else None,
        latency_p95_ms=int(percentile(latencies, 0.95)) if latencies else None,
        attempts=dict(sorted(Counter(r.attempts for r in results).items())),
    )


# --- run config facts --------------------------------------------------------------------------


def schema_hash() -> str:
    """Hash of the JSON schema that is actually sent to the model."""
    sent = anthropic.transform_schema(ExtractionResult)
    return hashlib.sha256(json.dumps(sent, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _git(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def git_state() -> tuple[str | None, bool | None]:
    """(HEAD SHA, whether the working tree has uncommitted changes); None when git is unavailable."""
    sha = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    return sha or None, None if status is None else bool(status)


def build_run_config(
    *,
    model_id: str,
    prompt_version: str,
    ingestion_path: IngestionPath,
    generator_version: dict[str, str] | None,
    max_concurrency: int,
    spend_cap_usd: Decimal,
    complete: bool,
    timestamp: datetime | None = None,
) -> RunConfig:
    sha, dirty = git_state()
    return RunConfig(
        model_id=model_id,
        prompt_version=prompt_version,
        schema_hash=schema_hash(),
        anthropic_version=metadata.version("anthropic"),
        pydantic_version=metadata.version("pydantic"),
        ingestion_path=ingestion_path,
        generator_version=generator_version,
        git_sha=sha,
        git_dirty=dirty,
        timestamp=timestamp or datetime.now(UTC),
        max_concurrency=max_concurrency,
        spend_cap_usd=spend_cap_usd,
        complete=complete,
    )


def make_run_id(config: RunConfig) -> str:
    short_sha = config.git_sha[:7] if config.git_sha else "nogit"
    return f"{config.timestamp:%Y%m%d-%H%M%S}-path_{config.ingestion_path}-{short_sha}"


def runs_dir(dataset: Literal["synthetic", "real"], root: Path = RUNS_DIR) -> Path:
    """Where a dataset's run records go. The real set is third-party personal data: git-ignored subdirectory."""
    return root / REAL_RUNS_DIRNAME if dataset == "real" else root


# --- persistence -------------------------------------------------------------------------------


def write_run_record(directory: Path, run_id: str, record: RunRecord) -> tuple[Path, Path]:
    """Write `<run_id>.json` and `<run_id>.jsonl`; returns their paths."""
    holds_real = any(r.entry.source == "real" for r in record.results)
    if holds_real and directory.name != REAL_RUNS_DIRNAME:
        raise ValueError(
            f"run records over the real set contain personal data and must be written under a "
            f"'{REAL_RUNS_DIRNAME}' directory, not {directory}"
        )
    directory.mkdir(parents=True, exist_ok=True)
    meta_path, documents_path = directory / f"{run_id}.json", directory / f"{run_id}.jsonl"
    meta = {
        "run_id": run_id,
        "config": record.config.model_dump(mode="json"),
        "aggregates": record.aggregates.model_dump(mode="json"),
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    documents_path.write_text(
        "".join(result.model_dump_json() + "\n" for result in record.results), encoding="utf-8"
    )
    return meta_path, documents_path


def read_run_record(directory: Path, run_id: str) -> RunRecord:
    meta = json.loads((directory / f"{run_id}.json").read_text(encoding="utf-8"))
    lines = (directory / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines()
    results = [DocumentResult.model_validate_json(line) for line in lines if line.strip()]
    record = RunRecord(
        config=RunConfig.model_validate(meta["config"]),
        aggregates=Aggregates.model_validate(meta["aggregates"]),
        results=results,
    )
    if record.aggregates != aggregate(results):
        raise ValueError(f"run record {run_id} is inconsistent: its aggregates do not match its documents")
    return record
