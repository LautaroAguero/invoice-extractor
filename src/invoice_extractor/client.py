"""Instrumented, failure-aware structured-output call (PRD 01 R2, design D9/D10).

The client is generic over the output model and knows nothing about invoices. Each call
returns a `CallRecord` describing only that call; nothing accumulates across calls.
"""

import time
from decimal import Decimal
from typing import Any, Generic, Literal, Protocol, TypeVar

import anthropic
from anthropic.types import Message
from pydantic import BaseModel, ConfigDict, ValidationError

from invoice_extractor.config import ExtractorConfig

T = TypeVar("T", bound=BaseModel)

FailureKind = Literal["truncated", "refused", "invalid_output", "api_error"]

_TRUNCATED_STOP_REASONS = {"max_tokens", "model_context_window_exceeded"}
# Every later call would fail the same way, so these stop the run instead of becoming records.
_CONFIGURATION_ERRORS = (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError)


class Messages(Protocol):
    async def create(self, **kwargs: Any) -> Message: ...


class SdkClient(Protocol):
    """The narrow slice of `anthropic.AsyncAnthropic` this module uses."""

    @property
    def messages(self) -> Messages: ...


class Parsed(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)

    kind: Literal["parsed"] = "parsed"
    value: T


class CallFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: FailureKind
    detail: str
    errors: list[dict[str, Any]] = []


class CallRecord(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)

    outcome: Parsed[T] | CallFailure
    model_id: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    latency_ms: int
    cost_usd: Decimal
    request_id: str | None


class ModelClient:
    def __init__(self, config: ExtractorConfig, sdk: SdkClient) -> None:
        self._config = config
        self._sdk = sdk

    @classmethod
    def from_config(cls, config: ExtractorConfig, **sdk_kwargs: Any) -> "ModelClient":
        """Build the real SDK client with the configured transport retry ceiling and timeout.

        `sdk_kwargs` pass through to `AsyncAnthropic` (e.g. `api_key`, `http_client` in tests).
        """
        sdk = anthropic.AsyncAnthropic(
            max_retries=config.max_retries, timeout=config.timeout_seconds, **sdk_kwargs
        )
        return cls(config, sdk)

    async def call(
        self,
        *,
        system: str,
        content: list[dict[str, Any]],
        output_model: type[T],
        max_tokens: int | None = None,
    ) -> CallRecord[T]:
        model = self._config.model
        self._config.price_for(model)  # unknown model: fail before any request is sent
        request = {
            "model": model,
            "max_tokens": max_tokens or self._config.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
            "output_config": {"format": {"type": "json_schema", "schema": anthropic.transform_schema(output_model)}},
        }

        started = time.perf_counter()
        try:
            message = await self._sdk.messages.create(**request)
        except _CONFIGURATION_ERRORS:
            raise
        except anthropic.APIStatusError as exc:
            detail = f"HTTP {exc.status_code} {type(exc).__name__}: {exc.message}"
            return _api_error(output_model, model, started, detail, exc.request_id)
        except anthropic.APIConnectionError as exc:
            return _api_error(output_model, model, started, f"{type(exc).__name__}: {exc}", None)
        latency_ms = _elapsed_ms(started)

        return CallRecord[output_model](
            outcome=_outcome(message, output_model),
            model_id=message.model or model,
            stop_reason=message.stop_reason,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            cache_read_input_tokens=message.usage.cache_read_input_tokens or 0,
            cache_creation_input_tokens=message.usage.cache_creation_input_tokens or 0,
            latency_ms=latency_ms,
            cost_usd=self._config.cost_usd(model, message.usage),
            request_id=getattr(message, "_request_id", None),
        )



def _api_error(
    output_model: type[T], model: str, started: float, detail: str, request_id: str | None
) -> CallRecord[T]:
    # No response: no usage to bill. Latency still covers every transport attempt.
    return CallRecord[output_model](
        outcome=CallFailure(kind="api_error", detail=detail),
        model_id=model,
        stop_reason=None,
        input_tokens=0,
        output_tokens=0,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        latency_ms=_elapsed_ms(started),
        cost_usd=Decimal(0),
        request_id=request_id,
    )


def _outcome(message: Message, output_model: type[T]) -> Parsed[T] | CallFailure:
    # The stop reason is checked before the output is read: a cut response is never parsed.
    if message.stop_reason in _TRUNCATED_STOP_REASONS:
        return CallFailure(kind="truncated", detail=f"stop_reason={message.stop_reason}")
    if message.stop_reason == "refusal":
        return CallFailure(kind="refused", detail="stop_reason=refusal")

    text = "".join(block.text for block in message.content if block.type == "text")
    if not text:
        return CallFailure(kind="invalid_output", detail="response has no text block")
    try:
        return Parsed[output_model](value=output_model.model_validate_json(text))
    except ValidationError as exc:
        return CallFailure(
            kind="invalid_output",
            detail=f"{exc.error_count()} validation error(s) against {output_model.__name__}",
            errors=exc.errors(include_url=False, include_context=False, include_input=False),
        )


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
