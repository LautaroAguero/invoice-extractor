import json
from datetime import date
from decimal import Decimal

import anthropic
import pytest
from pydantic import ValidationError

from invoice_extractor.schema import Extracted, ExtractionResult, Failed, Invoice


def validate(payload: dict) -> ExtractionResult:
    # Validate from JSON text, the same path the model's response takes.
    return ExtractionResult.model_validate_json(json.dumps(payload))


def failed(reason: str = "not_an_invoice", **extra) -> dict:
    return {"result": {"outcome": "failed", "reason": reason, "detail": "a remito", **extra}}


# --- 4.1 envelope --------------------------------------------------------------------


def test_extracted_result_exposes_invoice(spike_payload):
    result = validate(spike_payload).result
    assert isinstance(result, Extracted)
    assert isinstance(result.invoice, Invoice)


def test_failed_result_has_no_invoice():
    result = validate(failed()).result
    assert isinstance(result, Failed)
    assert result.reason == "not_an_invoice"
    assert not hasattr(result, "invoice")


def test_failed_result_carrying_invoice_is_rejected(invoice_payload):
    with pytest.raises(ValidationError):
        validate(failed(invoice=invoice_payload))


def test_result_with_neither_branch_is_rejected():
    with pytest.raises(ValidationError):
        validate({"result": {"outcome": "partial"}})


def test_unknown_failure_reason_is_rejected():
    with pytest.raises(ValidationError):
        validate(failed(reason="low_confidence"))


@pytest.mark.parametrize(
    "reason", ["not_an_invoice", "unsupported_document_type", "illegible", "missing_mandatory_data"]
)
def test_every_failure_reason_is_accepted(reason):
    assert validate(failed(reason=reason)).result.reason == reason


# --- 4.2 fields, mandatory/optional, enums ----------------------------------------------


def test_missing_mandatory_field_is_rejected(spike_payload, invoice_payload):
    del invoice_payload["cae"]["number"]
    with pytest.raises(ValidationError):
        validate(spike_payload)


def test_empty_items_is_rejected(spike_payload, invoice_payload):
    invoice_payload["items"] = []
    with pytest.raises(ValidationError):
        validate(spike_payload)


def test_consumer_invoice_without_customer_identity(spike_payload, invoice_payload):
    invoice_payload["invoice_type"] = "B"
    invoice_payload["customer"] = {"name": None, "cuit": None, "address": None, "vat_condition": "consumidor_final"}
    customer = validate(spike_payload).result.invoice.customer
    assert (customer.name, customer.cuit, customer.address) == (None, None, None)


def test_factura_b_without_discriminated_vat(spike_payload, invoice_payload):
    invoice_payload["invoice_type"] = "B"
    invoice_payload.update(net_amount=None, vat_amount=None, vat_breakdown=[])
    for item in invoice_payload["items"]:
        item["vat_rate"] = None
    invoice = validate(spike_payload).result.invoice
    assert invoice.net_amount is None and invoice.vat_amount is None and invoice.vat_breakdown == []


def test_omitted_list_is_rejected(spike_payload, invoice_payload):
    del invoice_payload["other_taxes"]
    with pytest.raises(ValidationError):
        validate(spike_payload)


def test_omitted_optional_key_is_rejected(spike_payload, invoice_payload):
    # Absent optional values are explicit null, never omitted keys (PRD 02 R3.3).
    del invoice_payload["due_date"]
    with pytest.raises(ValidationError):
        validate(spike_payload)


def test_unsupported_invoice_letter_is_rejected(spike_payload, invoice_payload):
    invoice_payload["invoice_type"] = "M"
    with pytest.raises(ValidationError):
        validate(spike_payload)


def test_catch_all_vat_condition_is_rejected(spike_payload, invoice_payload):
    invoice_payload["issuer"]["vat_condition"] = "other"
    with pytest.raises(ValidationError):
        validate(spike_payload)


def test_other_tax_line_is_represented(spike_payload, invoice_payload):
    invoice_payload["other_taxes"] = [{"description": "Percepción IIBB", "amount": "5000.00"}]
    (tax,) = validate(spike_payload).result.invoice.other_taxes
    assert tax.description == "Percepción IIBB" and tax.amount == Decimal("5000.00")


def test_item_from_spike_row(spike_payload):
    item = validate(spike_payload).result.invoice.items[1]
    assert item.code == "HW-220"
    assert item.quantity == Decimal("2")
    assert item.discount == Decimal("0")
    assert item.unit_price == Decimal("48500.00")
    assert item.vat_rate == Decimal("21")
    assert item.line_amount == Decimal("97000.00")


def test_item_has_no_unit_or_line_vat_fields():
    assert set(Invoice.model_fields["items"].annotation.__args__[0].model_fields) == {
        "code", "description", "quantity", "unit_price", "discount", "vat_rate", "line_amount",
    }


# --- 4.3 encoding ------------------------------------------------------------------------


def test_decimal_string_parses_exactly(spike_payload, invoice_payload):
    invoice_payload["total"] = "99999999999999.99"
    total = validate(spike_payload).result.invoice.total
    assert isinstance(total, Decimal)
    assert total == Decimal("99999999999999.99")


@pytest.mark.parametrize("bad", ["338.650,00", "1e3", "338650.", " 338650.00", ""])
def test_malformed_decimal_string_is_rejected(spike_payload, invoice_payload, bad):
    invoice_payload["total"] = bad
    with pytest.raises(ValidationError):
        validate(spike_payload)


def test_json_number_amount_is_rejected(spike_payload, invoice_payload):
    invoice_payload["total"] = 338650.00
    with pytest.raises(ValidationError):
        validate(spike_payload)


def test_iso_date(spike_payload):
    assert validate(spike_payload).result.invoice.issue_date == date(2026, 8, 12)


def test_point_of_sale_keeps_leading_zeros(spike_payload):
    assert validate(spike_payload).result.invoice.point_of_sale == "00003"


def test_wrong_length_cae_still_validates(spike_payload, invoice_payload):
    invoice_payload["cae"]["number"] = "7632145896321"
    assert validate(spike_payload).result.invoice.cae.number == "7632145896321"


def test_inconsistent_totals_still_validate(spike_payload, invoice_payload):
    invoice_payload["total"] = "1.00"
    assert validate(spike_payload).result.invoice.total == Decimal("1.00")


# --- 4.4 schema as the model sees it ------------------------------------------------------


@pytest.fixture(scope="module")
def sent_schema() -> dict:
    """The schema after the SDK's transform, i.e. what the API receives."""
    return anthropic.transform_schema(ExtractionResult)


def _objects(schema: dict):
    """Yield (path, object schema) for the root and every $defs object."""
    yield "ExtractionResult", schema
    for name, definition in schema["$defs"].items():
        if definition.get("type") == "object":
            yield name, definition


def test_every_property_description_reaches_the_model(sent_schema):
    defs = sent_schema["$defs"]
    missing = []
    for name, obj in _objects(sent_schema):
        for prop, prop_schema in obj["properties"].items():
            if "$ref" in prop_schema:
                target = defs[prop_schema["$ref"].rsplit("/", 1)[-1]]
                described = bool(target.get("description"))
            else:
                described = bool(prop_schema.get("description"))
            if not described:
                missing.append(f"{name}.{prop}")
    assert missing == []


def test_every_nested_object_has_a_description(sent_schema):
    assert [name for name, obj in _objects(sent_schema) if not obj.get("description")] == []


def test_no_confidence_field(sent_schema):
    names = {prop.lower() for _, obj in _objects(sent_schema) for prop in obj["properties"]}
    assert not {n for n in names if any(word in n for word in ("confidence", "certainty", "score"))}


def test_outcome_tags_are_constrained_in_the_grammar(sent_schema):
    defs = sent_schema["$defs"]
    assert defs["Extracted"]["properties"]["outcome"]["enum"] == ["extracted"]
    assert defs["Failed"]["properties"]["outcome"]["enum"] == ["failed"]
    assert "discriminator" not in json.dumps(sent_schema)


def _object_depth(model) -> int:
    """Object levels below `model` (a direct nested object or list of objects counts as 1)."""
    depths = [0]
    for field in model.model_fields.values():
        for arg in _flatten(field.annotation):
            if isinstance(arg, type) and hasattr(arg, "model_fields"):
                depths.append(1 + _object_depth(arg))
    return max(depths)


def _flatten(annotation):
    args = getattr(annotation, "__args__", None)
    if not args:
        return [annotation]
    return [leaf for arg in args for leaf in _flatten(arg)]


def test_invoice_nesting_is_at_most_two_levels():
    assert _object_depth(Invoice) <= 2


def test_course_minimum():
    fields = Invoice.model_fields
    nested = [f for f in fields.values() if isinstance(f.annotation, type) and hasattr(f.annotation, "model_fields")]
    lists = [f for f in fields.values() if getattr(f.annotation, "__origin__", None) is list]
    enums = [f for f in fields.values() if getattr(f.annotation, "__origin__", None) is not None and "Literal" in repr(f.annotation)]
    optional = [f for f in fields.values() if type(None) in _flatten(f.annotation)]
    assert len(fields) >= 8
    assert len(nested) >= 2
    assert len(lists) >= 1
    assert len(enums) >= 1
    assert len(optional) >= 2


# --- 4.5 fixture ------------------------------------------------------------------------------


def test_spike_fixture_matches_printed_key_values(spike_payload):
    invoice = validate(spike_payload).result.invoice
    assert invoice.total == Decimal("338650.00")
    assert invoice.issuer.cuit == "30712345671"
    assert invoice.customer.cuit == "30687654311"
    assert (invoice.point_of_sale, invoice.invoice_number) == ("00003", "00001542")
    assert invoice.cae.number == "76321458963214"
