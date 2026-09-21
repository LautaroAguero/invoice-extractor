"""Typed access to a dataset manifest and its ground truth (PRD 03 R1, R5; design D1)."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from invoice_extractor.schema import FailureReason, ExtractionResult

REPO_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_DIR = REPO_ROOT / "ground_truth"
REAL_DIR = REPO_ROOT / "ground_truth_real"

ExpectedOutcome = Literal["extracted", "explicit_failure"]
Source = Literal["synthetic", "real"]


class DocumentEntry(BaseModel):
    # The manifest carries generator and review metadata this stage does not use.
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    file: str
    format: Literal["pdf", "jpg"]
    source: Source
    tags: list[str]
    expected_outcome: ExpectedOutcome
    expected_reason: FailureReason | None
    generator_version: dict[str, str] | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    directory: Path
    entries: list[DocumentEntry]

    def document_path(self, entry: DocumentEntry) -> Path:
        return self.directory / entry.file

    def load_ground_truth(self, entry: DocumentEntry) -> ExtractionResult:
        path = self.directory / f"{entry.id}.json"
        return ExtractionResult.model_validate_json(path.read_text(encoding="utf-8"))

    @property
    def generator_version(self) -> dict[str, str] | None:
        """The generator provenance shared by the synthetic documents; None for the real set."""
        versions = {tuple(sorted(e.generator_version.items())) for e in self.entries if e.generator_version}
        if len(versions) > 1:
            raise ValueError("manifest mixes documents rendered by different generator versions")
        return dict(next(iter(versions))) if versions else None


def load_manifest(directory: Path = SYNTHETIC_DIR) -> Manifest:
    lines = (directory / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    entries = [DocumentEntry.model_validate_json(line) for line in lines if line.strip()]
    return Manifest(directory=directory, entries=entries)
