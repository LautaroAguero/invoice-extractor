"""Model, transport and price configuration (PRD 01 R2.6, design D11)."""

import tomllib
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, ValidationError

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "extractor.toml"
_PER_MILLION = Decimal(1_000_000)


class ConfigError(RuntimeError):
    """The configuration is missing, malformed, or has no entry for the requested model."""


class Usage(Protocol):
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int | None
    cache_creation_input_tokens: int | None


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelPrice(_Strict):
    """USD per million tokens for one model; cache multipliers apply to the input price."""

    input: Decimal
    output: Decimal
    cache_read_multiplier: Decimal
    cache_write_multiplier: Decimal
    verified_on: date


class ExtractorConfig(_Strict):
    model: str
    max_tokens: PositiveInt
    timeout_seconds: PositiveFloat
    # Transport retries are capped; the SDK's own default is not relied on (CC-4).
    max_retries: int = Field(ge=0, le=10)
    prices: dict[str, ModelPrice]

    def price_for(self, model: str) -> ModelPrice:
        try:
            return self.prices[model]
        except KeyError:
            raise ConfigError(f"no price entry for model {model!r}; add it to the price table") from None

    def cost_usd(self, model: str, usage: Usage) -> Decimal:
        """Cost of one call computed from its usage. Thinking tokens are already in output_tokens."""
        price = self.price_for(model)
        cache_read = usage.cache_read_input_tokens or 0
        cache_write = usage.cache_creation_input_tokens or 0
        micro_usd = (
            usage.input_tokens * price.input
            + usage.output_tokens * price.output
            + cache_read * price.input * price.cache_read_multiplier
            + cache_write * price.input * price.cache_write_multiplier
        )
        return micro_usd / _PER_MILLION


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> ExtractorConfig:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"config file is not valid TOML: {path}: {exc}") from None
    try:
        return ExtractorConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"invalid config {path}:\n{exc}") from None
