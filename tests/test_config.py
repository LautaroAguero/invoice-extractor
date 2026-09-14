from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from invoice_extractor.config import DEFAULT_CONFIG_PATH, ConfigError, ExtractorConfig, load_config


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None


PRICE_TOML = """
[prices.claude-sonnet-5]
input = "2.00"
output = "10.00"
cache_read_multiplier = "0.1"
cache_write_multiplier = "1.25"
verified_on = 2026-09-14
"""


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "extractor.toml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def config(tmp_path) -> ExtractorConfig:
    header = 'model = "claude-sonnet-5"\nmax_tokens = 16000\ntimeout_seconds = 120.0\nmax_retries = 3\n'
    return load_config(write_config(tmp_path, header + PRICE_TOML))


# --- 5.1 loading ---------------------------------------------------------------------------


def test_committed_config_loads_with_dated_prices():
    config = load_config(DEFAULT_CONFIG_PATH)
    assert config.model == "claude-sonnet-5"
    assert config.max_tokens == 16000
    assert set(config.prices) == {"claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"}
    assert all(isinstance(price.verified_on, date) for price in config.prices.values())


def test_missing_file_fails_loudly(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_missing_field_fails_loudly(tmp_path):
    body = 'model = "claude-sonnet-5"\nmax_tokens = 16000\ntimeout_seconds = 120.0\n' + PRICE_TOML  # no max_retries
    with pytest.raises(ConfigError, match="max_retries"):
        load_config(write_config(tmp_path, body))


def test_price_without_verification_date_fails_loudly(tmp_path):
    body = 'model = "m"\nmax_tokens = 1\ntimeout_seconds = 1.0\nmax_retries = 0\n' + PRICE_TOML.replace(
        "verified_on = 2026-09-14\n", ""
    )
    with pytest.raises(ConfigError, match="verified_on"):
        load_config(write_config(tmp_path, body))


def test_unbounded_retries_are_rejected(tmp_path):
    body = 'model = "m"\nmax_tokens = 1\ntimeout_seconds = 1.0\nmax_retries = 1000\n' + PRICE_TOML
    with pytest.raises(ConfigError, match="max_retries"):
        load_config(write_config(tmp_path, body))


# --- 5.2 cost ----------------------------------------------------------------------------------


def test_cost_from_input_and_output_tokens(config):
    assert config.cost_usd("claude-sonnet-5", FakeUsage(5_000, 2_000)) == Decimal("0.03")


def test_cache_read_tokens_use_their_multiplier(config):
    # 1M cache-read tokens at $2 x 0.1
    assert config.cost_usd("claude-sonnet-5", FakeUsage(0, 0, cache_read_input_tokens=1_000_000)) == Decimal("0.2")


def test_cache_creation_tokens_use_their_multiplier(config):
    # 1M cache-write tokens at $2 x 1.25
    assert config.cost_usd("claude-sonnet-5", FakeUsage(0, 0, cache_creation_input_tokens=1_000_000)) == Decimal("2.5")


def test_unknown_model_raises_configuration_error(config):
    with pytest.raises(ConfigError, match="claude-unknown"):
        config.cost_usd("claude-unknown", FakeUsage(1, 1))
