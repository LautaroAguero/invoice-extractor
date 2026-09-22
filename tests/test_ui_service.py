"""The UI's single call into the pipeline, with a fake SDK and no API key (PRD 06 R1.1, R2.4)."""

import json
from pathlib import Path

import pytest

from fakes import FakeSdk, make_message
from invoice_extractor.client import ModelClient, Parsed
from invoice_extractor.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from invoice_extractor.extraction import UnsupportedInputError
from invoice_extractor.prompts import load_prompt
from invoice_extractor.schema import Extracted
from invoice_extractor.ui import service

FAKE_PDF = b"%PDF-1.4 synthetic"


@pytest.fixture
def config():
    return load_config(DEFAULT_CONFIG_PATH)


def extracted_text(payload: dict) -> str:
    return json.dumps(payload)


def test_analyze_document_returns_the_record(tmp_path, config, spike_payload):
    path = tmp_path / "factura.pdf"
    path.write_bytes(FAKE_PDF)
    sdk = FakeSdk(make_message(extracted_text(spike_payload)))

    record = service.analyze_document(path, client=ModelClient(config, sdk), prompt=load_prompt("v1"))

    assert record.source == "factura.pdf"
    assert isinstance(record.call.outcome, Parsed)
    assert isinstance(record.call.outcome.value.result, Extracted)
    assert record.call.cost_usd > 0


def test_an_unsupported_file_is_rejected_before_any_call(tmp_path, config):
    path = tmp_path / "notes.txt"
    path.write_bytes(FAKE_PDF)
    sdk = FakeSdk(make_message("{}"))

    with pytest.raises(UnsupportedInputError):
        service.analyze_document(path, client=ModelClient(config, sdk), prompt=load_prompt("v1"))

    assert sdk.messages.requests == []


def test_missing_api_key_gives_an_actionable_message(config, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # python-dotenv searches from the caller's file, so a developer's real .env would load here.
    monkeypatch.setattr(service, "load_dotenv", lambda *args, **kwargs: False)

    with pytest.raises(ConfigError) as caught:
        service.build_client(config)

    assert "ANTHROPIC_API_KEY" in str(caught.value) and ".env" in str(caught.value)


def test_available_models_lists_the_configured_one_first(config):
    models = service.available_models(config)

    assert models[0] == config.model
    assert set(models) == set(config.prices)


def test_an_unpriced_model_is_rejected_before_any_request(config, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    with pytest.raises(ConfigError):
        service.build_client(config, "claude-unknown")


def test_the_page_module_is_the_only_one_importing_streamlit():
    ui_dir = Path(service.__file__).parent
    importing = {
        path.name for path in ui_dir.glob("*.py") if "import streamlit" in path.read_text(encoding="utf-8")
    }

    assert importing == {"app.py"}
