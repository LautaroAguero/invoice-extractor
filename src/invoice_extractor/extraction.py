"""Single-document extraction: prompt + document -> call record (design D12)."""

import base64
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from invoice_extractor.client import CallRecord, ModelClient
from invoice_extractor.prompts import Prompt
from invoice_extractor.schema import ExtractionResult

_PDF_MAGIC = b"%PDF-"


class UnsupportedInputError(ValueError):
    """The input is not a format this stage can send to the model (only PDF in stage 1)."""


class ExtractionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    prompt_version: str
    call: CallRecord[ExtractionResult]


def pdf_document_block(path: Path) -> dict:
    data = path.read_bytes()
    if path.suffix.lower() != ".pdf" or not data.startswith(_PDF_MAGIC):
        raise UnsupportedInputError(f"{path.name}: only PDF input is supported in this stage")
    return {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode("ascii")},
    }


async def extract_document(
    path: Path, *, client: ModelClient, prompt: Prompt, max_tokens: int | None = None
) -> ExtractionRecord:
    # Validated before the call: an unsupported file never costs a request.
    block = pdf_document_block(path)
    call = await client.call(system=prompt.text, content=[block], output_model=ExtractionResult, max_tokens=max_tokens)
    return ExtractionRecord(source=path.name, prompt_version=prompt.version, call=call)
