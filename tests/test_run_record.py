import json
import re
from decimal import Decimal
from importlib import metadata

import anthropic
import pytest

from builders import (
    extracted,
    failed,
    make_call,
    make_config,
    make_entry,
    make_record,
    make_result,
    perfect_result,
    truth_payload,
)
from invoice_extractor.client import CallFailure
from invoice_extractor.evaluation.run_record import (
    DocumentResult,
    RunConfig,
    aggregate,
    build_run_config,
    make_run_id,
    read_run_record,
    runs_dir,
    schema_hash,
    write_run_record,
)
from invoice_extractor.schema import ExtractionResult, Invoice


def _mixed_results() -> list[DocumentResult]:
    truth = Invoice.model_validate(truth_payload("A01"))
    wrong = truth_payload("A01")
    wrong["total"] = "1.00"
    return [
        perfect_result(make_entry("A01"), latency_ms=1_000, cost="0.010"),
        make_result(make_entry("A02"), extracted(wrong), truth, latency_ms=3_000, cost="0.020"),
        make_result(make_entry("A03"), failed("illegible"), truth, latency_ms=2_000, cost="0.005"),  # false rejection
        make_result(
            make_entry("remito", expected_outcome="explicit_failure", expected_reason="not_an_invoice"),
            failed("not_an_invoice"),
            latency_ms=500,
            cost="0.002",
        ),
        make_result(  # explicit failure without a model call
            make_entry("A05", tags=("skewed_scan",)), None, truth
        ),
    ]


# --- 6.1 config and document result ------------------------------------------------------------


def test_run_config_round_trips_through_json():
    config = make_config(spend_cap_usd=Decimal("2.50"))
    assert RunConfig.model_validate_json(config.model_dump_json()) == config


def test_document_result_round_trips_through_json():
    for result in _mixed_results():
        assert DocumentResult.model_validate_json(result.model_dump_json()) == result


def test_document_result_needs_exactly_one_of_a_call_or_a_reason():
    entry = make_entry("A01")
    with_call = make_result(entry, failed())
    with pytest.raises(ValueError):
        DocumentResult(**{**with_call.model_dump(), "no_call_reason": "no_text_layer"})
    with pytest.raises(ValueError):
        DocumentResult(**{**with_call.model_dump(), "extraction": None})


def test_schema_hash_is_the_hash_of_the_schema_actually_sent():
    import hashlib

    sent = anthropic.transform_schema(ExtractionResult)
    expected = hashlib.sha256(json.dumps(sent, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert schema_hash() == expected and len(expected) == 64


def test_built_config_records_versions_and_provenance():
    config = build_run_config(
        model_id="claude-sonnet-5",
        prompt_version="v1",
        ingestion_path="b",
        generator_version={"git_sha": "f7ff2e1"},
        max_concurrency=3,
        spend_cap_usd=Decimal("1"),
        complete=True,
    )
    assert config.anthropic_version == metadata.version("anthropic")
    assert config.pydantic_version == metadata.version("pydantic")
    assert config.schema_hash == schema_hash()
    assert config.git_sha is None or re.fullmatch(r"[0-9a-f]{40}", config.git_sha)
    assert config.timestamp.tzinfo is not None


def test_run_id_carries_time_path_and_short_sha():
    assert make_run_id(make_config()) == "20260917-120000-path_a-b8bc5d4"
    assert make_run_id(make_config(git_sha=None, ingestion_path="b")) == "20260917-120000-path_b-nogit"


# --- aggregates --------------------------------------------------------------------------------


def test_aggregates_sum_what_the_calls_reported():
    aggregates = aggregate(_mixed_results())

    assert aggregates.documents == 5
    assert aggregates.classifications == {
        "extraction": 2, "false_rejection": 2, "false_acceptance": 0, "correct_rejection": 1,  # A03 and the no-call A05
    }  # fmt: skip
    assert aggregates.total_cost_usd == Decimal("0.037")
    assert aggregates.input_tokens == 4 * 5_000 and aggregates.output_tokens == 4 * 2_000
    assert aggregates.attempts == {0: 1, 1: 4}


def test_latency_percentiles_ignore_documents_that_made_no_call():
    aggregates = aggregate(_mixed_results())  # calls took 500, 1000, 2000, 3000 ms; the no-call document is excluded
    assert aggregates.latency_p50_ms == 1_000
    assert aggregates.latency_p95_ms == 3_000


def test_aggregates_of_a_run_with_no_calls():
    aggregates = aggregate([make_result(make_entry("A05"), None, Invoice.model_validate(truth_payload("A01")))])
    assert aggregates.latency_p50_ms is None and aggregates.total_cost_usd == 0


def test_a_failed_call_costs_nothing_and_is_an_explicit_failure():
    result = make_result(
        make_entry("A01"),
        CallFailure(kind="api_error", detail="HTTP 529"),
        Invoice.model_validate(truth_payload("A01")),
        cost="0",
    )
    assert result.comparison.classification == "false_rejection"
    assert result.cost_usd == 0 and result.latency_ms == 1_000


# --- 6.2 persistence ---------------------------------------------------------------------------


def test_write_then_read_round_trips_a_run(tmp_path):
    record = make_record(_mixed_results())
    run_id = make_run_id(record.config)
    meta_path, documents_path = write_run_record(tmp_path, run_id, record)

    assert (meta_path.name, documents_path.name) == (f"{run_id}.json", f"{run_id}.jsonl")
    assert len(documents_path.read_text(encoding="utf-8").splitlines()) == 5
    assert json.loads(meta_path.read_text(encoding="utf-8"))["config"]["ingestion_path"] == "a"
    assert read_run_record(tmp_path, run_id) == record


def test_reading_a_record_whose_documents_were_edited_fails_loudly(tmp_path):
    record = make_record(_mixed_results())
    _, documents_path = write_run_record(tmp_path, "run", record)
    lines = documents_path.read_text(encoding="utf-8").splitlines()
    documents_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="inconsistent"):
        read_run_record(tmp_path, "run")


def test_real_set_records_are_written_only_under_the_real_directory(tmp_path):
    root = tmp_path / "runs"
    real_entry = make_entry("real_01", source="real", tags=("image_input",), fmt="jpg")
    record = make_record([make_result(real_entry, failed("illegible"), Invoice.model_validate(truth_payload("A01")))])

    with pytest.raises(ValueError, match="real"):
        write_run_record(root, "run", record)  # the committed location
    assert not root.exists()

    write_run_record(runs_dir("real", root), "run", record)
    assert [p.name for p in root.iterdir()] == ["real"]  # nothing at the top level of runs/


def test_runs_dir_keeps_the_synthetic_set_at_the_top_level(tmp_path):
    assert runs_dir("synthetic", tmp_path) == tmp_path
    assert runs_dir("real", tmp_path) == tmp_path / "real"


def test_incomplete_flag_survives_the_round_trip(tmp_path):
    record = make_record(_mixed_results(), complete=False)
    write_run_record(tmp_path, "run", record)
    assert read_run_record(tmp_path, "run").config.complete is False
