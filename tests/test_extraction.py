import asyncio
import base64
import io
import json
from pathlib import Path

import anthropic
import httpx2
import pytest

from fakes import FakeSdk, make_message
from invoice_extractor.client import ModelClient, Parsed
from invoice_extractor.config import DEFAULT_CONFIG_PATH, load_config
from invoice_extractor.extract_one import EXIT_EXTRACTED, EXIT_FAILURE, EXIT_USAGE, main
from invoice_extractor.extraction import UnsupportedInputError, extract_document
from invoice_extractor.prompts import PROMPTS_DIR, PromptNotFoundError, load_prompt
from invoice_extractor.schema import Extracted, ExtractionResult, Failed

FAKE_PDF = b"%PDF-1.4\n% synthetic test file\n"


@pytest.fixture
def pdf(tmp_path) -> Path:
    path = tmp_path / "spike_factura_a.pdf"
    path.write_bytes(FAKE_PDF)
    return path


@pytest.fixture
def config():
    return load_config(DEFAULT_CONFIG_PATH)


def extracted_text(spike_payload) -> str:
    return json.dumps(spike_payload)


# --- 7.1 prompt ---------------------------------------------------------------------------------


def test_v1_prompt_loads():
    prompt = load_prompt("v1")
    assert prompt.version == "v1"
    assert prompt.text == (PROMPTS_DIR / "v1.md").read_text(encoding="utf-8").strip()


def test_v1_prompt_has_no_examples_and_forbids_guessing():
    text = load_prompt("v1").text.lower()
    assert "never guess" in text
    assert "example" not in text and "{" not in text


@pytest.mark.parametrize("version", ["v9", "latest", "../config/extractor"])
def test_missing_or_invalid_version_raises(version):
    with pytest.raises(PromptNotFoundError):
        load_prompt(version)


def test_missing_prompt_version_fails_before_any_client_call(pdf, config, capsys):
    sdk = FakeSdk()
    code = main([str(pdf), "--prompt", "v9"], client=ModelClient(config, sdk))
    assert code == EXIT_USAGE
    assert sdk.messages.requests == []
    assert "PromptNotFoundError" in capsys.readouterr().err


# --- 7.2 extraction ---------------------------------------------------------------------------------


def test_message_layout_prompt_in_system_document_in_user_turn(pdf, config, spike_payload):
    sdk = FakeSdk(make_message(extracted_text(spike_payload)))
    prompt = load_prompt("v1")
    asyncio.run(extract_document(pdf, client=ModelClient(config, sdk), prompt=prompt))

    (request,) = sdk.messages.requests
    assert request["system"] == prompt.text
    (user_turn,) = request["messages"]
    assert user_turn["role"] == "user"
    (block,) = user_turn["content"]
    assert block == {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(FAKE_PDF).decode()},
    }
    assert request["output_config"]["format"]["schema"] == anthropic.transform_schema(ExtractionResult)


@pytest.mark.parametrize(
    ("name", "content"),
    [("scan.jpg", b"\xff\xd8\xff\xe0 jpeg"), ("renamed.pdf", b"\xff\xd8\xff\xe0 jpeg"), ("notes.txt", b"%PDF-1.4")],
)
def test_non_pdf_input_is_rejected_with_zero_calls(tmp_path, config, name, content):
    path = tmp_path / name
    path.write_bytes(content)
    sdk = FakeSdk()
    with pytest.raises(UnsupportedInputError):
        asyncio.run(extract_document(path, client=ModelClient(config, sdk), prompt=load_prompt("v1")))
    assert sdk.messages.requests == []


def test_fixture_flows_through_as_extracted_outcome(pdf, config, spike_payload):
    sdk = FakeSdk(make_message(extracted_text(spike_payload)))
    record = asyncio.run(extract_document(pdf, client=ModelClient(config, sdk), prompt=load_prompt("v1")))

    assert record.prompt_version == "v1"
    assert record.source == "spike_factura_a.pdf"
    assert isinstance(record.call.outcome, Parsed)
    result = record.call.outcome.value.result
    assert isinstance(result, Extracted)
    assert result.invoice.cae.number == "76321458963214"


def test_model_failure_flows_through(pdf, config):
    text = json.dumps({"result": {"outcome": "failed", "reason": "unsupported_document_type", "detail": "Nota de Crédito"}})
    record = asyncio.run(
        extract_document(pdf, client=ModelClient(config, FakeSdk(make_message(text))), prompt=load_prompt("v1"))
    )
    assert isinstance(record.call.outcome.value.result, Failed)


def test_api_error_flows_through_typed(pdf, config):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.BadRequestError("pdf too large", response=httpx2.Response(400, request=request), body=None)
    record = asyncio.run(
        extract_document(pdf, client=ModelClient(config, FakeSdk(error)), prompt=load_prompt("v1"))
    )
    assert record.call.outcome.kind == "api_error"


# --- 7.3 entry point --------------------------------------------------------------------------------


def run_main(argv, client) -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, client=client, out=out)
    return code, out.getvalue()


def test_truncated_call_prints_summary_and_exits_non_zero(pdf, config):
    sdk = FakeSdk(make_message('{"result": {"outc', stop_reason="max_tokens", input_tokens=4_000, output_tokens=64))
    code, output = run_main([str(pdf), "--max-tokens", "64"], ModelClient(config, sdk))

    assert code == EXIT_FAILURE
    assert sdk.messages.requests[0]["max_tokens"] == 64
    assert "outcome:     call failure (truncated)" in output
    assert "tokens:      in 4000 | out 64 | cache read 0 | cache write 0" in output
    assert "stop reason: max_tokens" in output
    assert "model:       claude-sonnet-5" in output
    assert "latency:" in output
    assert "cost:        $0.008640" in output
    assert "Traceback" not in output


def test_extracted_call_prints_summary_and_result(pdf, config, spike_payload):
    code, output = run_main([str(pdf)], ModelClient(config, FakeSdk(make_message(extracted_text(spike_payload)))))
    assert code == EXIT_EXTRACTED
    assert "outcome:     extracted" in output
    assert '"total": "338650.00"' in output


def test_model_failure_prints_reason(pdf, config):
    text = json.dumps({"result": {"outcome": "failed", "reason": "not_an_invoice", "detail": "a remito"}})
    code, output = run_main([str(pdf)], ModelClient(config, FakeSdk(make_message(text))))
    assert code == EXIT_FAILURE
    assert "outcome:     model failure (not_an_invoice): a remito" in output


def test_missing_api_key_exits_with_usage_error(pdf, monkeypatch, capsys):
    from invoice_extractor import extract_one

    monkeypatch.setattr(extract_one, "load_dotenv", lambda: None)  # never read a developer's real .env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main([str(pdf)]) == EXIT_USAGE
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY is not set" in err and "Traceback" not in err


def test_non_pdf_input_exits_with_usage_error(tmp_path, config, capsys):
    path = tmp_path / "scan.jpg"
    path.write_bytes(b"\xff\xd8")
    sdk = FakeSdk()
    assert main([str(path)], client=ModelClient(config, sdk)) == EXIT_USAGE
    assert sdk.messages.requests == []
    assert "UnsupportedInputError" in capsys.readouterr().err
