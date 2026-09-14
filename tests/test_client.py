import asyncio
import json
from decimal import Decimal

import anthropic
import httpx2
import pytest
from pydantic import BaseModel, Field

from fakes import FakeSdk, make_message
from invoice_extractor.client import CallFailure, CallRecord, ModelClient, Parsed
from invoice_extractor.config import ConfigError, ExtractorConfig, ModelPrice

PDF_BLOCK = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "JVBERi0="}}


class Weather(BaseModel):
    """An output model unrelated to invoices."""

    city: str = Field(description="City name.")
    temperatures: list[int] = Field(description="Readings.", min_length=1)


def make_config(model: str = "claude-sonnet-5", max_retries: int = 2) -> ExtractorConfig:
    price = ModelPrice(
        input=Decimal("2.00"), output=Decimal("10.00"),
        cache_read_multiplier=Decimal("0.1"), cache_write_multiplier=Decimal("1.25"),
        verified_on="2026-09-14",
    )
    return ExtractorConfig(
        model=model, max_tokens=16000, timeout_seconds=5.0, max_retries=max_retries,
        prices={"claude-sonnet-5": price},
    )


def call(client: ModelClient, **overrides) -> CallRecord:
    kwargs = {"system": "Extract.", "content": [PDF_BLOCK], "output_model": Weather} | overrides
    return asyncio.run(client.call(**kwargs))


WEATHER = json.dumps({"city": "Neuquén", "temperatures": [21, 23]})


def status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request, headers={"request-id": "req_err"})
    return cls("boom", response=response, body=None)


# --- 6.1 fake -------------------------------------------------------------------------------------


def test_fake_scripts_stop_reason_usage_and_output():
    sdk = FakeSdk(make_message(WEATHER, stop_reason="end_turn", input_tokens=7, output_tokens=3))
    message = asyncio.run(sdk.messages.create(model="m"))
    assert (message.stop_reason, message.usage.input_tokens, message.usage.output_tokens) == ("end_turn", 7, 3)
    assert json.loads(message.content[0].text)["city"] == "Neuquén"
    assert sdk.messages.requests == [{"model": "m"}]


# --- 6.2 structured call ---------------------------------------------------------------------------


def test_successful_call_populates_every_metric():
    sdk = FakeSdk(make_message(WEATHER, cache_read=100, cache_creation=10))
    record = call(ModelClient(make_config(), sdk))

    assert isinstance(record.outcome, Parsed)
    assert record.outcome.value == Weather(city="Neuquén", temperatures=[21, 23])
    assert record.model_id == "claude-sonnet-5"
    assert record.stop_reason == "end_turn"
    assert (record.input_tokens, record.output_tokens) == (5_000, 2_000)
    assert (record.cache_read_input_tokens, record.cache_creation_input_tokens) == (100, 10)
    assert record.latency_ms >= 0
    # 5000*2 + 2000*10 + 100*2*0.1 + 10*2*1.25 = 30045 micro-USD
    assert record.cost_usd == Decimal("0.030045")


def test_request_uses_native_structured_output_for_the_given_model():
    sdk = FakeSdk(make_message(WEATHER))
    call(ModelClient(make_config(), sdk), max_tokens=321)

    (request,) = sdk.messages.requests
    assert request["model"] == "claude-sonnet-5"
    assert request["max_tokens"] == 321
    assert request["system"] == "Extract."
    assert request["messages"] == [{"role": "user", "content": [PDF_BLOCK]}]
    assert request["output_config"] == {
        "format": {"type": "json_schema", "schema": anthropic.transform_schema(Weather)}
    }


def test_default_max_tokens_comes_from_config():
    sdk = FakeSdk(make_message(WEATHER))
    call(ModelClient(make_config(), sdk))
    assert sdk.messages.requests[0]["max_tokens"] == 16000


def test_records_are_independent():
    sdk = FakeSdk(
        make_message(WEATHER, input_tokens=1_000_000, output_tokens=0),
        make_message(WEATHER, input_tokens=0, output_tokens=1_000_000),
    )
    client = ModelClient(make_config(), sdk)
    first, second = call(client), call(client)
    assert (first.input_tokens, first.cost_usd) == (1_000_000, Decimal("2"))
    assert (second.input_tokens, second.output_tokens, second.cost_usd) == (0, 1_000_000, Decimal("10"))


def test_concurrent_calls_on_one_client():
    sdk = FakeSdk(make_message(WEATHER, input_tokens=1), make_message(WEATHER, input_tokens=2), delay=0.05)
    client = ModelClient(make_config(), sdk)

    async def both():
        return await asyncio.gather(
            client.call(system="s", content=[PDF_BLOCK], output_model=Weather),
            client.call(system="s", content=[PDF_BLOCK], output_model=Weather),
        )

    records = asyncio.run(both())
    assert sorted(r.input_tokens for r in records) == [1, 2]
    assert all(isinstance(r.outcome, Parsed) for r in records)


def test_client_keeps_no_cumulative_state():
    client = ModelClient(make_config(), FakeSdk(make_message(WEATHER)))
    call(client)
    assert not {name for name in vars(client) if any(w in name for w in ("usage", "cost", "total", "count"))}


# --- 6.3 stop reasons ----------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ['{"city": "Neu', None])
def test_max_tokens_is_a_truncated_failure(text):
    record = call(ModelClient(make_config(), FakeSdk(make_message(text, stop_reason="max_tokens"))))
    assert record.outcome == CallFailure(kind="truncated", detail="stop_reason=max_tokens")
    assert record.output_tokens == 2_000 and record.cost_usd == Decimal("0.03")


def test_context_window_exceeded_is_a_truncated_failure():
    record = call(ModelClient(make_config(), FakeSdk(make_message(None, stop_reason="model_context_window_exceeded"))))
    assert record.outcome.kind == "truncated"


def test_refusal_is_a_refused_failure_even_with_valid_json():
    record = call(ModelClient(make_config(), FakeSdk(make_message(WEATHER, stop_reason="refusal"))))
    assert record.outcome.kind == "refused"
    assert record.stop_reason == "refusal" and record.cost_usd == Decimal("0.03")


# --- 6.4 error mapping -----------------------------------------------------------------------------------


def test_validation_error_is_invalid_output_with_errors():
    bad = json.dumps({"city": "Neuquén", "temperatures": []})
    record = call(ModelClient(make_config(), FakeSdk(make_message(bad))))
    assert record.outcome.kind == "invalid_output"
    assert record.outcome.errors[0]["loc"] == ("temperatures",)
    assert record.cost_usd == Decimal("0.03")


def test_missing_text_block_is_invalid_output():
    record = call(ModelClient(make_config(), FakeSdk(make_message(None))))
    assert record.outcome.kind == "invalid_output"


@pytest.mark.parametrize(
    "error",
    [
        status_error(anthropic.BadRequestError, 400),
        status_error(anthropic.OverloadedError, 529),
        status_error(anthropic.RateLimitError, 429),
        anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")),
    ],
    ids=["400", "529", "429", "timeout"],
)
def test_request_errors_are_api_error_records(error):
    record = call(ModelClient(make_config(), FakeSdk(error)))
    assert record.outcome.kind == "api_error"
    assert (record.input_tokens, record.output_tokens, record.cost_usd) == (0, 0, Decimal(0))


@pytest.mark.parametrize(
    "error",
    [
        status_error(anthropic.AuthenticationError, 401),
        status_error(anthropic.PermissionDeniedError, 403),
        status_error(anthropic.NotFoundError, 404),
    ],
    ids=["401", "403", "404"],
)
def test_configuration_errors_are_raised(error):
    with pytest.raises(type(error)):
        call(ModelClient(make_config(), FakeSdk(error)))


def test_unknown_model_is_rejected_before_sending():
    sdk = FakeSdk(make_message(WEATHER))
    with pytest.raises(ConfigError):
        call(ModelClient(make_config(model="claude-unknown"), sdk))
    assert sdk.messages.requests == []


def test_real_sdk_retries_overload_up_to_the_ceiling():
    attempts = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        attempts.append(request.headers.get("x-stainless-retry-count"))
        # retry-after-ms keeps the test fast; the SDK honours it instead of its backoff.
        return httpx2.Response(529, headers={"retry-after-ms": "1"}, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})

    client = ModelClient.from_config(
        make_config(max_retries=2),
        api_key="test-key-not-real",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    record = call(client)

    assert attempts == ["0", "1", "2"]
    assert record.outcome.kind == "api_error"
    assert "529" in record.outcome.detail
