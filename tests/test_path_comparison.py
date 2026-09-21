import asyncio
import json
from decimal import Decimal

import pytest

from builders import extracted, failed, make_entry, make_record, make_result, truth_payload
from fakes import FakeSdk, make_message
from invoice_extractor.client import ModelClient
from invoice_extractor.config import DEFAULT_CONFIG_PATH, load_config
from invoice_extractor.evaluation.manifest import SYNTHETIC_DIR, Manifest, load_manifest
from invoice_extractor.evaluation.path_comparison import (
    compare_paths,
    compare_records,
    render_comparison_markdown,
    render_comparison_terminal,
)
from invoice_extractor.evaluation.run_record import IncompleteRunError
from invoice_extractor.evaluation.stats import mcnemar_exact
from invoice_extractor.prompts import load_prompt
from invoice_extractor.schema import Invoice

TRUTH = Invoice.model_validate(truth_payload("A01"))


# --- 10.1 running both paths ----------------------------------------------------------------------


def _text(payload: dict) -> str:
    return json.dumps({"result": {"outcome": "extracted", "invoice": payload}})


def test_both_paths_run_over_the_same_documents_and_the_coverage_group_is_the_unreadable_ones():
    manifest = load_manifest(SYNTHETIC_DIR)
    subset = Manifest(directory=manifest.directory, entries=[e for e in manifest.entries if e.id in ("A01", "A05", "A09", "remito")])
    wrong_total = truth_payload("A01")
    wrong_total["total"] = "1.00"
    not_an_invoice = json.dumps({"result": {"outcome": "failed", "reason": "not_an_invoice", "detail": "remito"}})
    illegible = json.dumps({"result": {"outcome": "failed", "reason": "illegible", "detail": "scan"}})
    # one client, sequential runs: path A calls A01, A05, A09, remito; then path B calls A01 and remito only
    sdk = FakeSdk(
        make_message(_text(truth_payload("A01"))),
        make_message(illegible),
        make_message(illegible),
        make_message(not_an_invoice),
        make_message(_text(wrong_total)),
        make_message(_text(truth_payload("A01"))),  # path B accepts the remito: a false acceptance
    )
    client = ModelClient(load_config(DEFAULT_CONFIG_PATH), sdk)

    run_a, run_b = asyncio.run(
        compare_paths(subset, client, load_prompt("v1"), max_concurrency=1, spend_cap_usd=Decimal("10"))
    )

    assert (run_a.config.ingestion_path, run_b.config.ingestion_path) == ("a", "b")
    assert [r.entry.id for r in run_a.results] == [r.entry.id for r in run_b.results] == ["A01", "A05", "A09", "remito"]
    assert len(sdk.messages.requests) == 6  # 4 + 2: path B made no call for the scan or the JPG

    comparison = compare_records(run_a, run_b)
    assert {e.id: e.reason for e in comparison.coverage} == {"A05": "no_text_layer", "A09": "image_input"}
    assert all(e.path_a_classification == "false_rejection" for e in comparison.coverage)
    assert comparison.paired_documents == 2  # A01 and remito
    assert comparison.a.correct_outcome.successes == 2 and comparison.b.correct_outcome.successes == 1
    assert comparison.a.cost_usd_per_document == Decimal("0.03") and comparison.b.cost_usd_per_document == Decimal("0.015")
    assert comparison.verdict.winner == "a"


def test_path_b_is_not_started_when_path_a_is_cut_short_by_its_cap():
    manifest = load_manifest(SYNTHETIC_DIR)
    subset = Manifest(directory=manifest.directory, entries=[e for e in manifest.entries if e.id in ("A01", "A02", "A03")])
    sdk = FakeSdk(*[make_message(_text(truth_payload("A01"))) for _ in range(3)])
    client = ModelClient(load_config(DEFAULT_CONFIG_PATH), sdk)

    run_a, run_b = asyncio.run(
        compare_paths(subset, client, load_prompt("v1"), max_concurrency=1, spend_cap_usd=Decimal("0.03"))
    )

    assert run_a.config.complete is False and len(run_a.results) == 1
    assert run_b is None
    assert len(sdk.messages.requests) == 1  # no money spent on a comparison that cannot be made


# --- 10.2 the paired result, checked against a hand calculation -----------------------------------------


def _doc(doc_id, **kwargs):
    return make_entry(doc_id, **kwargs)


def _ok(doc_id, **kw):
    return make_result(_doc(doc_id), extracted(truth_payload("A01")), TRUTH, **kw)


def _wrong_total(doc_id, **kw):
    payload = truth_payload("A01")
    payload["total"] = "1.00"
    return make_result(_doc(doc_id), extracted(payload), TRUTH, **kw)


def _rejected(doc_id, **kw):
    return make_result(_doc(doc_id), failed("illegible"), TRUTH, **kw)


def _no_call(doc_id):
    return make_result(_doc(doc_id, fmt="jpg", tags=("image_input",)), None, TRUTH)


def _records():
    """Six in-domain documents. Only D6 is unreadable for path B; D1..D5 are attempted by both.

    Correct outcome A: D1 D2 D3 D4 D6 (5/6). B: D1 D5 (2/6).
    Discordant among the attempted D1..D5: only A correct = D2 D3 D4 (3), only B correct = D5 (1).
    """
    a = [_ok("D1"), _ok("D2"), _ok("D3"), _ok("D4"), _rejected("D5"), _ok("D6")]
    b = [_wrong_total("D1"), _rejected("D2"), _rejected("D3"), _rejected("D4"), _ok("D5"), _no_call("D6")]
    return make_record(a, ingestion_path="a"), make_record(b, ingestion_path="b")


def test_mcnemar_counts_match_a_hand_calculation():
    comparison = compare_records(*_records())

    assert (comparison.documents, comparison.paired_documents) == (6, 5)
    assert (comparison.a_only_correct, comparison.b_only_correct) == (3, 1)
    # n = 4 discordant pairs, smaller count 1: p = 2 * (C(4,0) + C(4,1)) / 2^4 = 10/16
    assert comparison.mcnemar_p == pytest.approx(0.625) == mcnemar_exact(3, 1)


def test_unreadable_documents_are_reported_apart_and_kept_out_of_the_paired_test():
    comparison = compare_records(*_records())

    (entry,) = comparison.coverage
    assert (entry.id, entry.reason, entry.path_a_classification, entry.tags) == ("D6", "image_input", "extraction", ["image_input"])
    assert comparison.b.correct_outcome.n == 6  # coverage still counts against path B in its own totals


def test_field_deltas_use_only_the_documents_both_paths_extracted():
    comparison = compare_records(*_records())

    assert comparison.both_extracted == 1  # D1: A perfect, B has a wrong total
    deltas = {d.name: d for d in comparison.field_deltas}
    assert (deltas["total"].a.successes, deltas["total"].b.successes, deltas["total"].a.n) == (1, 0, 1)
    assert deltas["total"].delta_points == pytest.approx(-100.0)
    assert deltas["issuer.cuit"].delta_points == 0.0
    assert deltas["other_taxes_per_entry"].delta_points is None  # no entries to compare


def test_result_table_reports_precision_invented_values_cost_and_p95_latency_per_path():
    a = [_ok("D1", cost="0.010", latency_ms=1_000), _ok("D2", cost="0.010", latency_ms=3_000)]
    b = [_ok("D1", cost="0.004", latency_ms=500), _ok("D2", cost="0.004", latency_ms=800)]
    comparison = compare_records(make_record(a, ingestion_path="a"), make_record(b, ingestion_path="b"))

    assert comparison.a.cost_usd_per_document == Decimal("0.010") and comparison.b.cost_usd_per_document == Decimal("0.004")
    assert (comparison.a.p95_latency_ms, comparison.b.p95_latency_ms) == (3_000, 800)
    assert comparison.a.extraction_rate.successes == comparison.b.extraction_rate.successes == 2
    assert comparison.a.invented_values == comparison.b.invented_values == 0


def test_the_winner_is_named_with_its_trade_off():
    verdict = compare_records(*_records()).verdict

    assert verdict.winner == "a"
    assert "Path A wins: 5/6 correct outcomes against 2/6" in verdict.summary
    assert "cannot read 1 of 6 documents" in verdict.summary
    assert "McNemar exact p = 0.625" in verdict.summary and "within the noise" in verdict.summary


def test_equal_correct_outcomes_go_to_the_cheaper_path():
    a = [_ok("D1", cost="0.010"), _ok("D2", cost="0.010")]
    b = [_ok("D1", cost="0.004"), _ok("D2", cost="0.004")]
    verdict = compare_records(make_record(a, ingestion_path="a"), make_record(b, ingestion_path="b")).verdict
    assert verdict.winner == "b"


def test_identical_paths_are_a_tie():
    a = [_ok("D1", cost="0.010")]
    b = [_ok("D1", cost="0.010")]
    assert compare_records(make_record(a, ingestion_path="a"), make_record(b, ingestion_path="b")).verdict.winner == "tie"


def test_a_significant_gap_is_called_distinguishable_from_noise():
    a = [_ok(f"D{i}") for i in range(8)]
    b = [_rejected(f"D{i}") for i in range(8)]
    verdict = compare_records(make_record(a, ingestion_path="a"), make_record(b, ingestion_path="b")).verdict
    assert "distinguishable from noise" in verdict.summary  # 8 vs 0 discordant: p = 2/256


# --- guards --------------------------------------------------------------------------------------


def test_the_runs_must_be_a_then_b():
    run_a, run_b = _records()
    with pytest.raises(ValueError, match="path A run first"):
        compare_records(run_b, run_a)


def test_the_runs_must_cover_the_same_documents():
    run_a, _ = _records()
    other = make_record([_ok("D1")], ingestion_path="b")
    with pytest.raises(ValueError, match="same documents"):
        compare_records(run_a, other)


def test_an_incomplete_run_cannot_be_compared():
    run_a, run_b = _records()
    incomplete = make_record(list(run_b.results), ingestion_path="b", complete=False)
    with pytest.raises(IncompleteRunError):
        compare_records(run_a, incomplete)


def test_real_documents_are_not_part_of_the_comparison():
    run_a, run_b = _records()
    real_a = make_result(make_entry("real_01", source="real", fmt="jpg"), extracted(truth_payload("A01")), TRUTH)
    real_b = make_result(make_entry("real_01", source="real", fmt="jpg"), None, TRUTH)
    with_real = compare_records(
        make_record([*run_a.results, real_a], ingestion_path="a"), make_record([*run_b.results, real_b], ingestion_path="b")
    )
    assert with_real == compare_records(run_a, run_b)


# --- rendering -----------------------------------------------------------------------------------


def test_renderings_show_the_winner_the_coverage_group_and_stay_ascii():
    comparison = compare_records(*_records())
    terminal, markdown = render_comparison_terminal(comparison), render_comparison_markdown(comparison)

    for text in (terminal, markdown):
        text.encode("ascii")  # Windows consoles cannot print anything else
        assert "D6" in text and "image_input" in text
        assert "Path A wins" in text
        assert "McNemar" in text
    assert "WINNER  path A" in terminal
    assert "total" in terminal and "-100.0" in terminal
    assert "| `total` | 1/1 | 0/1 | -100.0 |" in markdown
