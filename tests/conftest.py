import copy
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def _spike_payload() -> dict:
    return json.loads((FIXTURES / "spike_factura_a.extraction.json").read_text(encoding="utf-8"))


@pytest.fixture
def spike_payload(_spike_payload) -> dict:
    """The spike Factura A as a JSON-decoded extraction result; safe to mutate."""
    return copy.deepcopy(_spike_payload)


@pytest.fixture
def invoice_payload(spike_payload) -> dict:
    return spike_payload["result"]["invoice"]
