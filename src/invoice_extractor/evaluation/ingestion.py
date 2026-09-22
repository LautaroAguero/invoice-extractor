"""How a document reaches the model: the two ingestion paths (PRD 03 R5, design D1).

Path A sends the file as a native document or image block. Path B extracts the text layer locally
with pdfplumber and sends only that text. Path B has no OCR, so a document with no text layer, and
every image, ends in an explicit failure without a model call instead of an extraction from empty
text (R5.3).

Both paths reach the model through `ModelClient.call`, so API errors, timeouts, rate limits and
truncated, refused or invalid output are handled there, exactly as for path A.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

from invoice_extractor.client import ModelClient
from invoice_extractor.evaluation.manifest import DocumentEntry
from invoice_extractor.evaluation.run_record import IngestionPath, NoCallReason
from invoice_extractor.extraction import (
    IMAGE_SUFFIXES,
    PDF_MAGIC,
    SUPPORTED,
    ExtractionRecord,
    UnsupportedInputError,
    extract_document,
)
from invoice_extractor.prompts import Prompt
from invoice_extractor.schema import ExtractionResult


@dataclass(frozen=True)
class NoCall:
    """The document ended in an explicit failure without any model call (path B, PRD 03 R5.3)."""

    reason: NoCallReason


Extractor = Callable[[DocumentEntry, Path, ModelClient, Prompt], Awaitable[ExtractionRecord | NoCall]]


async def extract_path_a(entry: DocumentEntry, path: Path, client: ModelClient, prompt: Prompt) -> ExtractionRecord:
    """Path A: the file goes to the model as a native document or image block."""
    return await extract_document(path, client=client, prompt=prompt)


def extract_text_pages(path: Path) -> str | None:
    """The text layer of a PDF: pdfplumber's default `extract_text()` on every page, joined by newlines.

    Returns `None` when no page has any text, which is what a scanned page looks like.
    """
    with pdfplumber.open(path) as pdf:
        pages = [page.extract_text() for page in pdf.pages]
    text = "\n".join(page for page in pages if page and page.strip())
    return text or None


def _require_pdf(path: Path) -> None:
    with path.open("rb") as handle:
        if path.suffix.lower() != ".pdf" or not handle.read(len(PDF_MAGIC)) == PDF_MAGIC:
            raise UnsupportedInputError(f"{path.name}: {SUPPORTED}")


async def extract_path_b(entry: DocumentEntry, path: Path, client: ModelClient, prompt: Prompt) -> ExtractionRecord | NoCall:
    """Path B: the PDF's own text is sent as a text block. Images, text-less and unparseable PDFs are explicit failures."""
    if path.suffix.lower() in IMAGE_SUFFIXES:
        return NoCall("image_input")
    _require_pdf(path)  # before any work: an unsupported file never costs a request
    try:
        text = await asyncio.to_thread(extract_text_pages, path)  # pdfplumber is synchronous; keep the loop free
    except PdfminerException:
        # A PDF that starts right but cannot be parsed is that document's outcome, not a reason to stop the run.
        return NoCall("unreadable_pdf")
    if text is None:
        return NoCall("no_text_layer")
    call = await client.call(
        system=prompt.text, content=[{"type": "text", "text": text}], output_model=ExtractionResult
    )
    return ExtractionRecord(source=path.name, prompt_version=prompt.version, call=call)


EXTRACTORS: dict[IngestionPath, Extractor] = {"a": extract_path_a, "b": extract_path_b}
