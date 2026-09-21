"""Single-document extraction: prompt + document -> call record (design D12)."""

import base64
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from invoice_extractor.client import CallRecord, ModelClient
from invoice_extractor.prompts import Prompt
from invoice_extractor.schema import ExtractionResult

PDF_MAGIC = b"%PDF-"
JPEG_MAGIC = b"\xff\xd8\xff"
JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})


class UnsupportedInputError(ValueError):
    """The input is not a format the extractor can send to the model (PDF and JPEG only)."""


class ExtractionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    prompt_version: str
    call: CallRecord[ExtractionResult]


def _base64_source(data: bytes, media_type: str) -> dict:
    return {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode("ascii")}


def pdf_document_block(path: Path) -> dict:
    data = path.read_bytes()
    if path.suffix.lower() != ".pdf" or not data.startswith(PDF_MAGIC):
        raise UnsupportedInputError(f"{path.name}: only PDF and JPG input is supported")
    return {"type": "document", "source": _base64_source(data, "application/pdf")}


def image_block(path: Path) -> dict:
    data = path.read_bytes()
    if path.suffix.lower() not in JPEG_SUFFIXES or not data.startswith(JPEG_MAGIC):
        raise UnsupportedInputError(f"{path.name}: only PDF and JPG input is supported")
    return {"type": "image", "source": _base64_source(data, "image/jpeg")}


def document_content_block(path: Path) -> dict:
    """The native content block for a file: image block for a JPEG, document block for anything else."""
    if path.suffix.lower() in JPEG_SUFFIXES:
        return image_block(path)
    return pdf_document_block(path)


async def extract_document(
    path: Path, *, client: ModelClient, prompt: Prompt, max_tokens: int | None = None
) -> ExtractionRecord:
    # Validated before the call: an unsupported file never costs a request.
    block = document_content_block(path)
    call = await client.call(system=prompt.text, content=[block], output_model=ExtractionResult, max_tokens=max_tokens)
    return ExtractionRecord(source=path.name, prompt_version=prompt.version, call=call)
