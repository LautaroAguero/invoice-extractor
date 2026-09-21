import asyncio
import json
from decimal import Decimal

import pytest

from builders import truth_payload
from fakes import FakeSdk, make_message
from invoice_extractor.client import ModelClient
from invoice_extractor.config import DEFAULT_CONFIG_PATH, load_config
from invoice_extractor.evaluation.execute import execute
from invoice_extractor.evaluation.ingestion import EXTRACTORS, NoCall, extract_path_a, extract_path_b, extract_text_pages
from invoice_extractor.evaluation.manifest import SYNTHETIC_DIR, Manifest, load_manifest
from invoice_extractor.extraction import UnsupportedInputError
from invoice_extractor.prompts import load_prompt

MANIFEST = load_manifest(SYNTHETIC_DIR)
ENTRIES = {e.id: e for e in MANIFEST.entries}


@pytest.fixture
def config():
    return load_config(DEFAULT_CONFIG_PATH)


def _path(doc_id: str):
    return MANIFEST.document_path(ENTRIES[doc_id])


def _perfect_text() -> str:
    return json.dumps({"result": {"outcome": "extracted", "invoice": truth_payload("A01")}})


def run_b(doc_id: str, sdk, config):
    client = ModelClient(config, sdk)
    return asyncio.run(extract_path_b(ENTRIES[doc_id], _path(doc_id), client, load_prompt("v1")))


# --- 9.1 text extraction -------------------------------------------------------------------------


def test_a_pdf_with_a_text_layer_yields_its_text():
    text = extract_text_pages(_path("A01"))
    truth = truth_payload("A01")

    assert text
    assert truth["cae"]["number"] in text
    assert truth["issuer"]["name"] in text


def test_item_rows_are_kept_whole_on_one_line():
    # the pdfplumber default mode was chosen because it keeps a row's cells together (PRD 03 OQ-3.1)
    first_row = truth_payload("A01")["items"][0]
    lines = extract_text_pages(_path("A01")).splitlines()
    assert any(first_row["description"] in line and first_row["code"] in line for line in lines)


def test_every_page_of_a_multi_page_document_is_read():
    text = extract_text_pages(_path("A03"))
    items = truth_payload("A03")["items"]
    assert items[0]["description"] in text and items[-1]["description"] in text


def test_a_scanned_pdf_has_no_text_layer():
    assert extract_text_pages(_path("A05")) is None


def test_only_the_skewed_scans_lack_a_text_layer():
    # the premise of PRD 03 R5.3, checked against the whole synthetic dataset
    without_text = {
        e.id for e in MANIFEST.entries if e.format == "pdf" and extract_text_pages(MANIFEST.document_path(e)) is None
    }
    assert without_text == {e.id for e in MANIFEST.entries if "skewed_scan" in e.tags}


# --- 9.2 path B ----------------------------------------------------------------------------------


def test_a_text_bearing_pdf_is_sent_as_a_single_text_block(config):
    sdk = FakeSdk(make_message(_perfect_text()))
    record = run_b("A01", sdk, config)

    (request,) = sdk.messages.requests
    (user_turn,) = request["messages"]
    assert user_turn["content"] == [{"type": "text", "text": extract_text_pages(_path("A01"))}]
    assert request["system"] == load_prompt("v1").text
    assert record.source == "A01.pdf" and record.call.outcome.kind == "parsed"


@pytest.mark.parametrize(("doc_id", "reason"), [("A05", "no_text_layer"), ("C05", "no_text_layer"), ("A09", "image_input"), ("B07", "image_input")])
def test_documents_path_b_cannot_read_end_in_an_explicit_failure_without_a_call(config, doc_id, reason):
    sdk = FakeSdk()
    assert run_b(doc_id, sdk, config) == NoCall(reason)
    assert sdk.messages.requests == []


def test_an_unsupported_file_is_rejected_before_any_work(tmp_path, config):
    path = tmp_path / "notes.txt"
    path.write_bytes(b"%PDF-1.4 but named txt")
    sdk = FakeSdk()
    with pytest.raises(UnsupportedInputError):
        asyncio.run(extract_path_b(ENTRIES["A01"], path, ModelClient(config, sdk), load_prompt("v1")))
    assert sdk.messages.requests == []


def test_a_pdf_named_file_that_is_not_a_pdf_is_rejected(tmp_path, config):
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(UnsupportedInputError):
        asyncio.run(extract_path_b(ENTRIES["A01"], path, ModelClient(config, FakeSdk()), load_prompt("v1")))


def test_both_paths_are_registered():
    assert EXTRACTORS == {"a": extract_path_a, "b": extract_path_b}


# --- path B through the executor -------------------------------------------------------------------


def test_the_executor_records_no_call_documents_as_false_rejections_that_cost_nothing(config):
    subset = Manifest(directory=MANIFEST.directory, entries=[ENTRIES[i] for i in ("A01", "A05", "A09")])
    sdk = FakeSdk(make_message(_perfect_text()))

    record = asyncio.run(
        execute(subset, ModelClient(config, sdk), load_prompt("v1"), ingestion_path="b", max_concurrency=2, spend_cap_usd=Decimal("1"))
    )

    by_id = {r.entry.id: r for r in record.results}
    assert record.config.ingestion_path == "b" and record.config.complete
    assert len(sdk.messages.requests) == 1  # only A01 reached the model
    assert by_id["A01"].comparison.classification == "extraction"
    for doc_id, reason in (("A05", "no_text_layer"), ("A09", "image_input")):
        result = by_id[doc_id]
        assert result.no_call_reason == reason and result.extraction is None
        assert result.attempts == 0 and result.cost_usd == 0
        assert result.comparison.classification == "false_rejection"  # explicit failure, never an extraction
    assert record.aggregates.attempts == {0: 2, 1: 1}


def test_a_pdf_that_cannot_be_parsed_is_that_documents_outcome_not_a_crash(tmp_path, config):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\n% starts like a PDF but has no structure")
    sdk = FakeSdk()

    outcome = asyncio.run(extract_path_b(ENTRIES["A01"], broken, ModelClient(config, sdk), load_prompt("v1")))

    assert outcome == NoCall("unreadable_pdf")
    assert sdk.messages.requests == []


def test_an_unparseable_document_does_not_abort_the_run(tmp_path, config):
    from builders import write_dataset

    manifest = write_dataset(tmp_path, [("D01", "extracted"), ("D02", "extracted")])  # both are structureless PDFs
    record = asyncio.run(
        execute(manifest, ModelClient(config, FakeSdk()), load_prompt("v1"), ingestion_path="b", max_concurrency=2, spend_cap_usd=Decimal("1"))
    )
    assert record.config.complete and len(record.results) == 2
    assert {r.no_call_reason for r in record.results} == {"unreadable_pdf"}
