import asyncio
import json
from decimal import Decimal

import anthropic
import httpx2
import pytest

from builders import truth_payload, write_dataset
from fakes import RoutedSdk, make_message
from invoice_extractor.client import ModelClient
from invoice_extractor.config import DEFAULT_CONFIG_PATH, load_config
from invoice_extractor.evaluation.execute import execute
from invoice_extractor.prompts import load_prompt

COST_PER_CALL = Decimal("0.03")  # 5,000 in / 2,000 out at $2 / $10 per million tokens


def _perfect_text() -> str:
    return json.dumps({"result": {"outcome": "extracted", "invoice": truth_payload("A01")}})


def _wrong_total_text() -> str:
    invoice = truth_payload("A01")
    invoice["total"] = "1.00"
    return json.dumps({"result": {"outcome": "extracted", "invoice": invoice}})


def _not_an_invoice_text() -> str:
    return json.dumps({"result": {"outcome": "failed", "reason": "not_an_invoice", "detail": "a remito"}})


def _http_error(cls, status: int):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


@pytest.fixture
def config():
    return load_config(DEFAULT_CONFIG_PATH)


def run(manifest, sdk, config, **kwargs):
    kwargs.setdefault("max_concurrency", 3)
    kwargs.setdefault("spend_cap_usd", Decimal("100"))
    return asyncio.run(execute(manifest, ModelClient(config, sdk), load_prompt("v1"), **kwargs))


def _ids(count: int) -> list[tuple[str, str]]:
    return [(f"D{i:02d}", "extracted") for i in range(count)]


# --- 7.1 execution -------------------------------------------------------------------------------


def test_every_document_is_run_scored_and_independent(tmp_path, config):
    manifest = write_dataset(
        tmp_path, [("D01", "extracted"), ("D02", "extracted"), ("N01", "negative"), ("N02", "negative")]
    )
    answers = {"D01": _perfect_text(), "D02": _wrong_total_text(), "N01": _not_an_invoice_text(), "N02": _perfect_text()}
    sdk = RoutedSdk(lambda doc: make_message(answers[doc]))

    record = run(manifest, sdk, config)

    by_id = {r.entry.id: r for r in record.results}
    assert [r.entry.id for r in record.results] == ["D01", "D02", "N01", "N02"]  # manifest order
    assert by_id["D01"].comparison.classification == "extraction"
    assert all(f.status == "correct" for f in by_id["D01"].comparison.fields)
    assert {f.path for f in by_id["D02"].comparison.fields if f.status != "correct"} == {"total"}
    assert by_id["N01"].comparison.classification == "correct_rejection"
    assert by_id["N02"].comparison.classification == "false_acceptance"
    assert record.config.complete is True
    assert record.aggregates.documents == 4
    assert record.aggregates.total_cost_usd == 4 * COST_PER_CALL
    assert all(r.attempts == 1 for r in record.results)


def test_run_config_names_what_was_measured(tmp_path, config):
    manifest = write_dataset(tmp_path, _ids(1))
    record = run(manifest, RoutedSdk(lambda doc: make_message(_perfect_text())), config, max_concurrency=2)

    assert record.config.model_id == "claude-sonnet-5"
    assert record.config.prompt_version == "v1"
    assert record.config.ingestion_path == "a"
    assert record.config.max_concurrency == 2
    assert record.config.generator_version == {"git_sha": "f7ff2e1"}


def test_concurrency_is_bounded(tmp_path, config):
    manifest = write_dataset(tmp_path, _ids(10))
    sdk = RoutedSdk(lambda doc: make_message(_perfect_text()), delay=0.01)

    record = run(manifest, sdk, config, max_concurrency=3)

    assert len(record.results) == 10
    assert sdk.max_in_flight == 3


def test_sequential_run_never_overlaps_calls(tmp_path, config):
    manifest = write_dataset(tmp_path, _ids(4))
    sdk = RoutedSdk(lambda doc: make_message(_perfect_text()), delay=0.005)
    run(manifest, sdk, config, max_concurrency=1)
    assert sdk.max_in_flight == 1


@pytest.mark.parametrize(
    "kwargs", [{"max_concurrency": 0}, {"spend_cap_usd": Decimal(0)}, {"spend_cap_usd": Decimal(-1)}]
)
def test_limits_cannot_be_disabled(tmp_path, config, kwargs):
    manifest = write_dataset(tmp_path, _ids(1))
    sdk = RoutedSdk(lambda doc: make_message(_perfect_text()))
    with pytest.raises(ValueError):
        run(manifest, sdk, config, **kwargs)
    assert sdk.requests == []


def test_unknown_ingestion_path_is_rejected_before_any_call(tmp_path, config):
    manifest = write_dataset(tmp_path, _ids(1))
    sdk = RoutedSdk(lambda doc: make_message(_perfect_text()))
    with pytest.raises(ValueError, match="not available"):
        run(manifest, sdk, config, ingestion_path="z")
    assert sdk.requests == []


# --- 7.2 spend cap -------------------------------------------------------------------------------


def test_spend_cap_stops_the_run_and_marks_it_incomplete(tmp_path, config):
    manifest = write_dataset(tmp_path, _ids(10))
    sdk = RoutedSdk(lambda doc: make_message(_perfect_text()))

    record = run(manifest, sdk, config, max_concurrency=1, spend_cap_usd=Decimal("0.10"))

    # $0.03 per call: 0.03, 0.06, 0.09 are under the cap, the 4th call reaches 0.12 and nothing starts after it.
    assert [r.entry.id for r in record.results] == ["D00", "D01", "D02", "D03"]
    assert len(sdk.requests) == 4
    assert record.config.complete is False
    assert record.config.spend_cap_usd == Decimal("0.10")
    assert record.aggregates.total_cost_usd == Decimal("0.12")


def test_calls_in_flight_when_the_cap_is_hit_still_finish_and_are_recorded(tmp_path, config):
    manifest = write_dataset(tmp_path, _ids(12))
    sdk = RoutedSdk(lambda doc: make_message(_perfect_text()), delay=0.01)

    record = run(manifest, sdk, config, max_concurrency=3, spend_cap_usd=Decimal("0.05"))

    assert record.config.complete is False
    assert len(record.results) == len(sdk.requests) < 12  # every started call has its record
    assert record.aggregates.total_cost_usd == len(record.results) * COST_PER_CALL
    assert len(record.results) <= 2 + 3  # after two completed calls the cap is reached; at most 3 were in flight


def test_a_cap_reached_exactly_on_the_last_document_is_still_a_complete_run(tmp_path, config):
    manifest = write_dataset(tmp_path, _ids(3))
    sdk = RoutedSdk(lambda doc: make_message(_perfect_text()))
    record = run(manifest, sdk, config, max_concurrency=1, spend_cap_usd=Decimal("0.09"))
    assert len(record.results) == 3 and record.config.complete is True


# --- 7.3 one document's failure does not abort the run -------------------------------------------


def test_call_failures_are_that_documents_outcome_and_the_run_continues(tmp_path, config):
    manifest = write_dataset(tmp_path, _ids(5))
    behaviours = {
        "D01": _http_error(anthropic.BadRequestError, 400),
        "D02": make_message('{"result": {"outc', stop_reason="max_tokens", output_tokens=64),
        "D03": make_message(None, stop_reason="refusal"),
    }
    sdk = RoutedSdk(lambda doc: behaviours.get(doc, make_message(_perfect_text())))

    record = run(manifest, sdk, config)

    assert record.config.complete is True and len(record.results) == 5
    by_id = {r.entry.id: r for r in record.results}
    kinds = [by_id[d].extraction.call.outcome.kind for d in ("D01", "D02", "D03")]
    assert kinds == ["api_error", "truncated", "refused"]
    assert all(by_id[d].comparison.classification == "false_rejection" for d in ("D01", "D02", "D03"))
    assert all(by_id[d].comparison.classification == "extraction" for d in ("D00", "D04"))
    assert by_id["D01"].cost_usd == 0 and by_id["D02"].cost_usd > 0  # a truncated call is still billed


def test_a_failed_call_on_a_negative_counts_as_a_correct_rejection(tmp_path, config):
    manifest = write_dataset(tmp_path, [("N01", "negative")])
    sdk = RoutedSdk(lambda doc: _http_error(anthropic.BadRequestError, 400))
    (result,) = run(manifest, sdk, config).results
    assert result.comparison.classification == "correct_rejection"
    assert result.comparison.reason_agrees is False


def test_configuration_errors_abort_the_run_instead_of_becoming_records(tmp_path, config):
    manifest = write_dataset(tmp_path, _ids(4))
    sdk = RoutedSdk(lambda doc: _http_error(anthropic.AuthenticationError, 401))
    with pytest.raises(anthropic.AuthenticationError):
        run(manifest, sdk, config)


def test_an_exhausted_account_aborts_the_run(tmp_path, config):
    # Otherwise the run finishes "complete" with an api_error per document (run 20260922-195941).
    manifest = write_dataset(tmp_path, _ids(4))
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(400, request=request, headers={"request-id": "req_err"})
    error = anthropic.BadRequestError("Your credit balance is too low to access the API", response=response, body=None)
    sdk = RoutedSdk(lambda doc: error)

    with pytest.raises(anthropic.BadRequestError):
        run(manifest, sdk, config)
