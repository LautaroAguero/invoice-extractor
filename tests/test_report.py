import os
import re
from decimal import Decimal
from pathlib import Path

import pytest

from builders import extracted, failed, make_entry, make_record, make_result, perfect_result, truth_payload
from invoice_extractor.evaluation.report import build_report, render_markdown, render_terminal
from invoice_extractor.evaluation.run_record import IncompleteRunError
from invoice_extractor.evaluation.stats import wilson_interval
from invoice_extractor.schema import Invoice

TRUTH = Invoice.model_validate(truth_payload("A01"))


def _mutated(**changes):
    payload = truth_payload("A01")
    payload.update(changes)
    return extracted(payload)


def _first_item_misread():
    payload = truth_payload("A01")
    payload["items"][0]["unit_price"] = "1.00"
    return extracted(payload)


def synthetic_results():
    """Eight synthetic documents whose report numbers are worked out by hand in the tests below."""
    negative = dict(expected_outcome="explicit_failure")
    return [
        perfect_result(make_entry("A01"), cost="0.010", latency_ms=1_000),
        make_result(make_entry("A02", tags=("multi_page",)), _mutated(total="1.00"), TRUTH, cost="0.020", latency_ms=3_000),
        make_result(
            make_entry("A03", tags=("foreign_currency",)),
            _mutated(due_date=None, exchange_rate="1.00"),  # one missed value, one invented value
            TRUTH,
            cost="0.010",
            latency_ms=2_000,
        ),
        make_result(make_entry("A04", tags=("dense_table",)), _first_item_misread(), TRUTH, cost="0.010", latency_ms=1_500),
        make_result(make_entry("A05", tags=("skewed_scan",)), failed("illegible"), TRUTH, cost="0.005", latency_ms=4_000),
        make_result(  # correct rejection, reason agrees
            make_entry("N01", tags=("not_an_invoice",), expected_reason="not_an_invoice", **negative),
            failed("not_an_invoice"), None, cost="0.002", latency_ms=500,
        ),
        make_result(  # correct rejection, reason differs
            make_entry("N02", tags=("unsupported_document",), expected_reason="unsupported_document_type", **negative),
            failed("not_an_invoice"), None, cost="0.002", latency_ms=600,
        ),
        make_result(  # false acceptance
            make_entry("N03", tags=("not_an_invoice",), expected_reason="not_an_invoice", **negative),
            extracted(truth_payload("A01")), None, cost="0.010", latency_ms=2_500,
        ),
    ]  # fmt: skip


def real_results():
    # A01's invoice stands in for the real ground truth: tests never read the git-ignored personal data.
    real_01 = make_entry("real_01", source="real", tags=("image_input",), fmt="jpg")
    real_02 = make_entry("real_02", source="real", tags=("image_input",), fmt="jpg")
    return [
        make_result(real_01, extracted(truth_payload("A01")), TRUTH, cost="0.020"),
        make_result(real_02, failed("illegible"), TRUTH, cost="0.010"),
    ]


def _line(fields, name):
    return next(line for line in fields.fields if line.name == name)


def _assert_rate(rate, successes, n):
    assert (rate.successes, rate.n) == (successes, n)
    if n:
        assert (rate.low, rate.high) == wilson_interval(successes, n)
    else:
        assert rate.low is None and rate.high is None


# --- 8.1 sections computed by hand ---------------------------------------------------------------


def test_outcome_counts_and_rates():
    o = build_report(make_record(synthetic_results())).headline.outcomes

    assert (o.documents, o.in_domain, o.negatives) == (8, 5, 3)
    _assert_rate(o.correct_outcome, 6, 8)  # 4 extractions + 2 correct rejections
    _assert_rate(o.extraction_rate, 4, 5)  # of the 5 in-domain documents
    assert (o.false_rejections, o.correct_rejections, o.false_acceptances) == (1, 2, 1)
    _assert_rate(o.reason_agreement, 1, 2)
    assert (o.invented_values, o.missed_values) == (1, 1)


def test_field_precision_is_over_successful_extractions_only():
    fields = build_report(make_record(synthetic_results())).headline.fields

    assert fields.extractions == 4  # A01-A04; the false rejection and the negatives are not in the denominator
    for name in ("total", "due_date", "exchange_rate"):
        _assert_rate(_line(fields, name).rate, 3, 4)
    for name in ("invoice_type", "issuer.cuit", "cae.number", "customer.address"):
        _assert_rate(_line(fields, name).rate, 4, 4)


def test_list_metrics_report_exact_per_entry_and_extra_entries():
    fields = build_report(make_record(synthetic_results())).headline.fields

    _assert_rate(_line(fields, "items_exact").rate, 3, 4)
    _assert_rate(_line(fields, "items_per_entry").rate, 15, 16)  # 4 documents x 4 rows, one misread row
    assert _line(fields, "items_per_entry").extra_entries == 0
    _assert_rate(_line(fields, "vat_breakdown_exact").rate, 4, 4)
    _assert_rate(_line(fields, "vat_breakdown_per_entry").rate, 8, 8)
    _assert_rate(_line(fields, "other_taxes_exact").rate, 4, 4)
    _assert_rate(_line(fields, "other_taxes_per_entry").rate, 0, 0)  # no ground-truth entries: n/a, not 0%


def test_per_tag_breakdown_shows_where_failures_sit():
    by_tag = {t.tag: t for t in build_report(make_record(synthetic_results())).headline.by_tag}

    assert set(by_tag) == {
        "dense_table", "foreign_currency", "multi_page", "not_an_invoice", "skewed_scan",
        "unsupported_document", "(no tag)",
    }  # fmt: skip
    _assert_rate(by_tag["skewed_scan"].correct_outcome, 0, 1)  # the false rejection
    _assert_rate(by_tag["not_an_invoice"].correct_outcome, 1, 2)  # N01 rejected, N03 accepted
    _assert_rate(by_tag["dense_table"].correct_outcome, 1, 1)
    _assert_rate(by_tag["dense_table"].perfect_extractions, 0, 1)  # extracted, but a row is misread
    _assert_rate(by_tag["(no tag)"].perfect_extractions, 1, 1)
    _assert_rate(by_tag["skewed_scan"].perfect_extractions, 0, 0)  # no extraction to be perfect
    assert by_tag["multi_page"].documents == 1


def test_attempts_cost_and_latency_come_from_the_run_record():
    headline = build_report(make_record(synthetic_results())).headline

    assert headline.attempts == {1: 8}
    assert headline.cost.total_usd == Decimal("0.069")
    assert headline.cost.mean_usd_per_document == Decimal("0.069") / 8
    # sorted latencies: 500 600 1000 1500 2000 2500 3000 4000 -> nearest-rank p50 = 4th, p95 = 8th
    assert (headline.latency.p50_ms, headline.latency.p95_ms) == (1_500, 4_000)


def test_documents_without_a_call_lower_the_mean_cost_but_not_the_latency():
    results = [
        perfect_result(make_entry("A01"), cost="0.010", latency_ms=1_000),
        make_result(make_entry("A05", tags=("skewed_scan",)), None, TRUTH),
    ]
    headline = build_report(make_record(results)).headline

    assert headline.cost.mean_usd_per_document == Decimal("0.005")
    assert (headline.latency.p50_ms, headline.latency.p95_ms) == (1_000, 1_000)
    assert headline.attempts == {0: 1, 1: 1}


# --- 8.2 worst field -----------------------------------------------------------------------------


def test_the_worst_field_is_marked_automatically():
    results = synthetic_results()
    # make cae.expiry_date the clear worst: wrong in three of the four extractions
    payload = truth_payload("A01")
    payload["cae"]["expiry_date"] = "2030-01-01"
    for index in (0, 1, 3):
        results[index] = make_result(results[index].entry, extracted(payload), TRUTH)

    fields = build_report(make_record(results)).headline.fields

    assert fields.worst == "cae.expiry_date"
    _assert_rate(_line(fields, "cae.expiry_date").rate, 1, 4)


def test_worst_field_ties_are_broken_by_name():
    fields = build_report(make_record(synthetic_results())).headline.fields
    # due_date, exchange_rate and total are all 3/4; items_per_entry (15/16) is better
    assert fields.worst == "due_date"


def test_exact_list_lines_are_never_the_worst_field():
    payload = truth_payload("A01")
    payload["items"] = payload["items"][1:]  # every list-exact fails, every scalar stays right
    results = [make_result(make_entry(f"A0{i}"), extracted(payload), TRUTH) for i in range(1, 4)]

    fields = build_report(make_record(results)).headline.fields

    assert _line(fields, "items_exact").rate.successes == 0
    assert fields.worst == "items_per_entry"


def test_no_worst_field_when_every_scored_field_is_correct():
    results = [perfect_result(make_entry(f"A0{i}")) for i in range(1, 4)]
    fields = build_report(make_record(results)).headline.fields
    assert fields.extractions == 3 and fields.worst is None


def test_no_worst_field_when_nothing_was_extracted():
    results = [make_result(make_entry("A05"), failed("illegible"), TRUTH)]
    fields = build_report(make_record(results)).headline.fields
    assert fields.extractions == 0 and fields.worst is None


# --- 8.3 real set --------------------------------------------------------------------------------


def test_real_documents_never_enter_a_headline_number():
    without_real = build_report(make_record(synthetic_results()))
    with_real = build_report(make_record([*synthetic_results(), *real_results()]))

    assert with_real.headline == without_real.headline  # identical: counts, rates, fields, cost, latency
    assert with_real.headline.outcomes.documents == 8


def test_real_set_gets_its_own_section_without_intervals():
    real = build_report(make_record([*synthetic_results(), *real_results()])).real

    assert (real.documents, real.extractions, real.false_rejections) == (2, 1, 1)
    assert real.cost_usd == Decimal("0.030")
    assert real.fields.extractions == 1
    assert all(line.rate.low is None and line.rate.high is None for line in real.fields.fields)
    assert _line(real.fields, "total").rate.successes == 1


def test_a_run_over_only_the_real_set_has_no_headline():
    report = build_report(make_record(real_results()))
    assert report.headline is None and report.real.documents == 2


def test_a_run_without_real_documents_has_no_real_section():
    assert build_report(make_record(synthetic_results())).real is None


# --- 8.5 incomplete runs ---------------------------------------------------------------------------


def test_an_incomplete_run_is_refused():
    with pytest.raises(IncompleteRunError, match="incomplete"):
        build_report(make_record(synthetic_results(), complete=False))


# --- 8.4 rendering: snapshots of the fixture report -----------------------------------------------

SNAPSHOTS = Path(__file__).parent / "snapshots"


def _check_snapshot(name: str, text: str) -> None:
    """Compare with the committed snapshot; UPDATE_SNAPSHOTS=1 rewrites it, and the diff is reviewed in git."""
    path = SNAPSHOTS / name
    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAPSHOTS.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    assert text == path.read_text(encoding="utf-8"), f"{name} changed; rerun with UPDATE_SNAPSHOTS=1 and review the diff"


def _fixture_report():
    return build_report(make_record([*synthetic_results(), *real_results()]))


def test_terminal_report_snapshot():
    _check_snapshot("report_terminal.txt", render_terminal(_fixture_report()))


def test_markdown_report_snapshot():
    _check_snapshot("report_markdown.md", render_markdown(_fixture_report()))


def test_terminal_report_is_ascii_so_windows_consoles_can_print_it():
    render_terminal(_fixture_report()).encode("ascii")
    render_markdown(_fixture_report()).encode("ascii")


def test_every_rate_line_carries_its_n_and_an_interval():
    text = render_terminal(build_report(make_record(synthetic_results())))
    headline_lines = [l for l in text.splitlines() if re.search(r"\d\.\d%", l)]
    assert headline_lines
    for line in headline_lines:
        assert re.search(r"\d+/\d+", line), line  # its n
        assert "[" in line and "]" in line, line  # its 95% interval


def test_the_real_section_is_labelled_and_has_no_interval():
    text = render_terminal(_fixture_report())
    real_section = text.split("REAL SET", 1)[1]
    assert "NOT a headline number" in real_section
    assert "[" not in real_section


def test_the_real_section_is_absent_when_there_are_no_real_documents():
    assert "REAL SET" not in render_terminal(build_report(make_record(synthetic_results())))
    assert "Real set" not in render_markdown(build_report(make_record(synthetic_results())))
