import copy
import json
from datetime import date
from decimal import Decimal

import pytest

from invoice_extractor.evaluation.compare import (
    INVOICE_LEAVES,
    INVOICE_LISTS,
    actual_outcome,
    classify,
    compare,
    compare_list,
    compare_value,
    normalize,
)
from invoice_extractor.evaluation.manifest import SYNTHETIC_DIR
from invoice_extractor.schema import ExtractionResult, Invoice


def _truth_payload() -> dict:
    """A01's ground-truth invoice as a JSON-decoded dict; safe to mutate."""
    payload = json.loads((SYNTHETIC_DIR / "A01.json").read_text(encoding="utf-8"))
    return copy.deepcopy(payload["result"]["invoice"])


def _extracted(invoice: dict) -> ExtractionResult:
    return ExtractionResult.model_validate({"result": {"outcome": "extracted", "invoice": invoice}})


def _failed(reason: str = "not_an_invoice") -> ExtractionResult:
    return ExtractionResult.model_validate({"result": {"outcome": "failed", "reason": reason, "detail": "n/a"}})


@pytest.fixture
def truth() -> Invoice:
    return Invoice.model_validate(_truth_payload())


def _invoice(**changes) -> Invoice:
    payload = _truth_payload()
    payload.update(changes)
    return Invoice.model_validate(payload)


# --- 4.1 normalization --------------------------------------------------------------------------


def test_decimal_compares_by_numeric_value_not_by_text():
    assert normalize("decimal", "150000.00") == normalize("decimal", "150000")
    assert normalize("decimal", "150000.00") != normalize("decimal", "150000.01")


def test_date_is_iso_and_exact():
    assert normalize("date", "2026-07-27") == date(2026, 7, 27)
    assert normalize("date", date(2026, 7, 27)) == normalize("date", "2026-07-27")


def test_cuit_and_identifiers_keep_digits_only_with_leading_zeros():
    assert normalize("digits", "30-03186265-1") == "30031862651"
    assert normalize("digits", "00003-00001542") == "0000300001542"
    assert normalize("digits", "00005") == "00005"


def test_text_ignores_case_whitespace_and_unicode_form():
    assert normalize("text", "  Tecnored   PATAGONIA S.A. ") == normalize("text", "tecnored patagonia s.a.")
    assert normalize("text", "Migración") == normalize("text", "Migración")  # NFC vs NFD
    assert normalize("text", "Router AX3000") != normalize("text", "Router AX3001")


def test_enum_is_exact():
    assert normalize("enum", "ARS") == "ARS"
    assert normalize("enum", "ARS") != normalize("enum", "USD")


def test_none_stays_none():
    assert normalize("digits", None) is None


def test_schema_walk_covers_every_scored_field():
    assert {leaf.path for leaf in INVOICE_LEAVES} == {
        "invoice_type", "document_code", "point_of_sale", "invoice_number", "issue_date", "due_date",
        "issuer.name", "issuer.cuit", "issuer.vat_condition",
        "customer.name", "customer.cuit", "customer.address", "customer.vat_condition",
        "currency", "exchange_rate", "net_amount", "non_taxed_amount", "exempt_amount", "vat_amount", "total",
        "cae.number", "cae.expiry_date",
    }  # fmt: skip
    assert {name: [leaf.path for leaf in leaves] for name, leaves in INVOICE_LISTS.items()} == {
        "items": [f"items[].{f}" for f in ("code", "description", "quantity", "unit_price", "discount", "vat_rate", "line_amount")],
        "vat_breakdown": ["vat_breakdown[].rate", "vat_breakdown[].amount"],
        "other_taxes": ["other_taxes[].description", "other_taxes[].amount"],
    }  # fmt: skip


def test_schema_walk_assigns_the_documented_kinds():
    kinds = {leaf.path: leaf.kind for leaf in INVOICE_LEAVES}
    assert kinds["point_of_sale"] == kinds["cae.number"] == kinds["issuer.cuit"] == "digits"
    assert kinds["total"] == kinds["exchange_rate"] == "decimal"
    assert kinds["issue_date"] == kinds["cae.expiry_date"] == "date"
    assert kinds["currency"] == kinds["issuer.vat_condition"] == "enum"
    assert kinds["issuer.name"] == kinds["customer.address"] == "text"
    assert {l.path: l.kind for l in INVOICE_LISTS["items"]}["items[].code"] == "text"  # product code is not an identifier


# --- 4.2 scalar comparison: every row of the §2 table --------------------------------------------


@pytest.mark.parametrize(
    ("expected", "predicted", "status"),
    [
        ("30031862651", "30-03186265-1", "correct"),  # value, same value
        ("30031862651", "30031862652", "wrong"),  # value, different value
        ("30031862651", None, "missed"),  # value, null
        (None, None, "correct"),  # null, null
        (None, "30031862651", "invented"),  # null, value
    ],
)
def test_scalar_comparison_follows_the_section_2_table(expected, predicted, status):
    assert compare_value("digits", expected, predicted) == status


def test_amounts_have_no_tolerance():
    assert compare_value("decimal", Decimal("150000.00"), Decimal("150000")) == "correct"
    assert compare_value("decimal", Decimal("150000.00"), Decimal("150000.01")) == "wrong"


# --- 4.3 lists ---------------------------------------------------------------------------------


def _list(truth: Invoice, name: str, predicted: list):
    return compare_list(name, predicted, getattr(truth, name), INVOICE_LISTS[name])


def test_identical_list_is_exact(truth):
    result = _list(truth, "items", list(truth.items))
    assert result.exact and result.correct_entries == 4 and result.extra_entries == 0
    assert result.entry_errors == [] and not result.order_only_mismatch


def test_a_skipped_early_row_cascades_to_every_following_entry(truth):
    result = _list(truth, "items", list(truth.items[1:]))

    assert not result.exact
    assert result.correct_entries == 0  # rows 0-2 are compared against the shifted rows
    assert result.missing_entries == 1 and result.extra_entries == 0
    assert {e.path.split(".")[0] for e in result.entry_errors} == {"items[0]", "items[1]", "items[2]"}
    assert not result.order_only_mismatch


def test_extra_vat_entry_on_an_empty_ground_truth_list_counts_as_extra(truth):
    empty = truth.model_copy(update={"vat_breakdown": []})
    result = compare_list("vat_breakdown", list(truth.vat_breakdown[:1]), empty.vat_breakdown, INVOICE_LISTS["vat_breakdown"])

    assert result.expected_count == 0 and result.extra_entries == 1
    assert result.correct_entries == 0 and not result.exact


def test_two_empty_lists_are_exact(truth):
    assert compare_list("other_taxes", [], [], INVOICE_LISTS["other_taxes"]).exact


def test_same_entries_in_another_order_are_flagged_order_only(truth):
    result = _list(truth, "vat_breakdown", list(reversed(truth.vat_breakdown)))

    assert not result.exact and result.order_only_mismatch
    assert result.correct_entries == 0
    assert result.extra_entries == 0


def test_a_misread_value_is_not_order_only(truth):
    items = [i.model_copy(update={"unit_price": Decimal("1.00")}) if n == 0 else i for n, i in enumerate(truth.items)]
    result = _list(truth, "items", items)

    assert not result.exact and not result.order_only_mismatch
    assert result.correct_entries == 3
    assert [(e.path, e.status, e.expected, e.predicted) for e in result.entry_errors] == [
        ("items[0].unit_price", "wrong", "138300.00", "1.00")
    ]


# --- 4.4 document outcome: every cell of the §1 table -------------------------------------------


@pytest.mark.parametrize(
    ("expected", "actual", "classification"),
    [
        ("extracted", "extracted", "extraction"),
        ("extracted", "explicit_failure", "false_rejection"),
        ("explicit_failure", "extracted", "false_acceptance"),
        ("explicit_failure", "explicit_failure", "correct_rejection"),
    ],
)
def test_classification_matches_the_section_1_table(expected, actual, classification):
    assert classify(expected, actual) == classification


def test_a_call_with_no_result_is_an_explicit_failure(truth):
    assert actual_outcome(None) == "explicit_failure"
    assert actual_outcome(_failed()) == "explicit_failure"
    assert actual_outcome(_extracted(_truth_payload())) == "extracted"


# --- 4.5 end to end ---------------------------------------------------------------------------


def test_a_perfect_extraction_scores_every_field_correct(truth):
    result = compare(_extracted(_truth_payload()), truth, "extracted", None)

    assert result.classification == "extraction"
    assert len(result.fields) == 22 and all(f.status == "correct" for f in result.fields)
    assert [l.name for l in result.lists] == ["items", "vat_breakdown", "other_taxes"]
    assert all(l.exact for l in result.lists)
    assert result.invented_values == result.missed_values == 0
    assert result.reason_agrees is None


def test_a_mismatching_extraction_reports_wrong_missed_and_invented_values(truth):
    payload = _truth_payload()
    payload["total"] = "1.00"  # wrong
    payload["due_date"] = None  # missed
    payload["exchange_rate"] = "1.00"  # invented: ground truth is null
    payload["items"][1]["discount"] = None  # missed, inside an entry
    result = compare(_extracted(payload), truth, "extracted", None)

    statuses = {f.path: f.status for f in result.fields if f.status != "correct"}
    assert statuses == {"total": "wrong", "due_date": "missed", "exchange_rate": "invented"}
    assert result.invented_values == 1
    assert result.missed_values == 2
    items = next(l for l in result.lists if l.name == "items")
    assert not items.exact and items.correct_entries == 3
    assert [(e.path, e.status) for e in items.entry_errors] == [("items[1].discount", "missed")]


def test_false_rejection_scores_no_fields(truth):
    result = compare(_failed("illegible"), truth, "extracted", None)
    assert result.classification == "false_rejection"
    assert result.fields == [] and result.lists == []


def test_false_acceptance_needs_no_ground_truth_invoice():
    result = compare(_extracted(_truth_payload()), None, "explicit_failure", "not_an_invoice")
    assert result.classification == "false_acceptance"
    assert result.reason_agrees is None


def test_correct_rejection_reports_reason_agreement_without_changing_the_outcome():
    agree = compare(_failed("not_an_invoice"), None, "explicit_failure", "not_an_invoice")
    differ = compare(_failed("illegible"), None, "explicit_failure", "not_an_invoice")
    no_result = compare(None, None, "explicit_failure", "not_an_invoice")

    assert agree.classification == differ.classification == no_result.classification == "correct_rejection"
    assert (agree.reason_agrees, differ.reason_agrees, no_result.reason_agrees) == (True, False, False)
    assert differ.actual_reason == "illegible" and no_result.actual_reason is None


def test_extraction_without_ground_truth_is_an_error():
    with pytest.raises(ValueError):
        compare(_extracted(_truth_payload()), None, "extracted", None)


def test_comparison_result_survives_a_json_round_trip(truth):
    payload = _truth_payload()
    payload["total"] = "1.00"
    result = compare(_extracted(payload), truth, "extracted", None)

    from invoice_extractor.evaluation.compare import ComparisonResult

    assert ComparisonResult.model_validate_json(result.model_dump_json()) == result


def test_every_ground_truth_document_scores_perfectly_against_itself():
    from invoice_extractor.evaluation.manifest import load_manifest
    from invoice_extractor.schema import Extracted

    manifest = load_manifest(SYNTHETIC_DIR)
    in_domain = [e for e in manifest.entries if e.expected_outcome == "extracted"]
    assert len(in_domain) == 25
    for entry in in_domain:
        truth_result = manifest.load_ground_truth(entry)
        assert isinstance(truth_result.result, Extracted)
        result = compare(truth_result, truth_result.result.invoice, "extracted", None)
        assert all(f.status == "correct" for f in result.fields), entry.id
        assert all(l.exact for l in result.lists), entry.id
