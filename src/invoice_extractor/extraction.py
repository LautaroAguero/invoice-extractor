"""Single-document extraction: prompt + document -> call record (design D12)."""

import base64
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from invoice_extractor.client import CallRecord, ModelClient
from invoice_extractor.prompts import Prompt
from invoice_extractor.schema import ExtractionResult

PDF_MAGIC = b"%PDF-"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# suffix -> (media type, magic bytes). The bytes are checked too, so a file whose extension
# lies is rejected before it costs a request.
IMAGE_FORMATS: dict[str, tuple[str, bytes]] = {
    ".jpg": ("image/jpeg", JPEG_MAGIC),
    ".jpeg": ("image/jpeg", JPEG_MAGIC),
    ".png": ("image/png", PNG_MAGIC),
}
IMAGE_SUFFIXES = frozenset(IMAGE_FORMATS)
SUPPORTED = "only PDF, JPG and PNG input is supported"


class UnsupportedInputError(ValueError):
    """The input is not a format the extractor can send to the model (PDF, JPEG and PNG only)."""


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
        raise UnsupportedInputError(f"{path.name}: {SUPPORTED}")
    return {"type": "document", "source": _base64_source(data, "application/pdf")}


def image_block(path: Path) -> dict:
    data = path.read_bytes()
    media_type, magic = IMAGE_FORMATS.get(path.suffix.lower(), ("", b""))
    if not media_type or not data.startswith(magic):
        raise UnsupportedInputError(f"{path.name}: {SUPPORTED}")
    return {"type": "image", "source": _base64_source(data, media_type)}


def document_content_block(path: Path) -> dict:
    """The native content block for a file: image block for a JPEG or PNG, document block for anything else."""
    if path.suffix.lower() in IMAGE_SUFFIXES:
        return image_block(path)
    return pdf_document_block(path)


async def extract_document(
    path: Path, *, client: ModelClient, prompt: Prompt, max_tokens: int | None = None
) -> ExtractionRecord:
    # Validated before the call: an unsupported file never costs a request.
    block = document_content_block(path)
    call = await client.call(system=prompt.text, content=[block], output_model=ExtractionResult, max_tokens=max_tokens)
    return ExtractionRecord(source=path.name, prompt_version=prompt.version, call=call)
