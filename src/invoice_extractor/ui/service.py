"""The UI's only way into the pipeline (design D2).

Everything the page knows about extracting a document goes through `analyze_document`.
When `add-validation-and-iterations` lands, this function calls `process_document` instead
of `extract_document`, and the page does not change.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from invoice_extractor.client import ModelClient
from invoice_extractor.config import ConfigError, ExtractorConfig, load_config
from invoice_extractor.extraction import ExtractionRecord, extract_document
from invoice_extractor.prompts import Prompt

MISSING_KEY_MESSAGE = (
    "ANTHROPIC_API_KEY no está configurada. Copiá .env.example a .env y completá la clave, "
    "o exportá la variable antes de iniciar la aplicación."
)


def load_extractor_config() -> ExtractorConfig:
    return load_config()


def available_models(config: ExtractorConfig) -> list[str]:
    """Models that can be selected: those with a price entry, configured one first (design D7)."""
    others = sorted(name for name in config.prices if name != config.model)
    return [config.model, *others]


def build_client(config: ExtractorConfig, model: str | None = None) -> ModelClient:
    """The same client the CLI builds. Raises `ConfigError` when no API key is configured."""
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ConfigError(MISSING_KEY_MESSAGE)
    if model and model != config.model:
        config = config.model_copy(update={"model": model})
    config.price_for(config.model)  # an unpriced model fails before any request
    return ModelClient.from_config(config)


def analyze_document(
    path: Path, *, client: ModelClient, prompt: Prompt, max_tokens: int | None = None
) -> ExtractionRecord:
    """Process one document and return its record. The single call site of the page."""
    return asyncio.run(extract_document(path, client=client, prompt=prompt, max_tokens=max_tokens))
