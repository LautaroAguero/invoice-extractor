"""Ground-truth comparison per docs/measurement-rules.md §1-§4 (PRD 03 R2, design D3).

The scored fields are found by walking the `Invoice` model, not listed by hand. A field type the
walk does not recognise raises instead of being skipped, so a schema change cannot silently drop
a field from the measurement.
"""

import re
import unicodedata
from collections import Counter
from datetime import date
from decimal import Decimal
from types import UnionType
from typing import Annotated, Any, Literal, NamedTuple, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict

from invoice_extractor.evaluation.manifest import ExpectedOutcome
from invoice_extractor.schema import Extracted, ExtractionResult, Failed, FailureReason, Invoice

Kind = Literal["decimal", "date", "digits", "text", "enum"]
FieldStatus = Literal["correct", "wrong", "missed", "invented"]
Classification = Literal["extraction", "false_rejection", "false_acceptance", "correct_rejection"]

# §4: identifiers compared on their digits only, leading zeros preserved. Everything else that is a
# string is free text, including the product `code` of an item.
_DIGIT_PATHS = frozenset(
    {"document_code", "point_of_sale", "invoice_number", "issuer.cuit", "customer.cuit", "cae.number"}
)


# --- normalization (§4) --------------------------------------------------------------------------


def normalize(kind: Kind, value: Any) -> Any:
    """Canonical form used only for equality. `None` stays `None`."""
    if value is None:
        return None
    match kind:
        case "decimal":
            return value if isinstance(value, Decimal) else Decimal(str(value))
        case "date":
            return value if isinstance(value, date) else date.fromisoformat(value)
        case "digits":
            return re.sub(r"\D", "", str(value))
        case "text":
            folded = unicodedata.normalize("NFC", str(value)).casefold()
            return re.sub(r"\s+", " ", folded).strip()
        case "enum":
            return value
    raise ValueError(f"unknown comparison kind {kind!r}")


# --- scalar comparison (§2) ----------------------------------------------------------------------


def compare_value(kind: Kind, expected: Any, predicted: Any) -> FieldStatus:
    if expected is None:
        return "correct" if predicted is None else "invented"
    if predicted is None:
        return "missed"
    return "correct" if normalize(kind, expected) == normalize(kind, predicted) else "wrong"


# --- schema walk ---------------------------------------------------------------------------------


class _Leaf(NamedTuple):
    path: str
    chain: tuple[str, ...]
    kind: Kind


def _unwrap(annotation: Any) -> Any:
    """Strip `Annotated[...]` and `X | None` down to the underlying type."""
    while True:
        origin = get_origin(annotation)
        if origin is Annotated:
            annotation = get_args(annotation)[0]
        elif origin in (Union, UnionType):
            members = [a for a in get_args(annotation) if a is not type(None)]
            if len(members) != 1:
                raise TypeError(f"cannot score a union of several types: {annotation!r}")
            annotation = members[0]
        else:
            return annotation


def _kind_of(annotation: Any, path: str) -> Kind:
    if get_origin(annotation) is Literal:
        return "enum"
    if annotation is Decimal:
        return "decimal"
    if annotation is date:
        return "date"
    if annotation is str:
        return "digits" if path in _DIGIT_PATHS else "text"
    raise TypeError(f"no comparison kind for field {path!r} of type {annotation!r}")


def _leaves(model: type[BaseModel], prefix: str = "", chain: tuple[str, ...] = ()) -> list[_Leaf]:
    """The scalar leaves of a model with nested models flattened. Lists are scored separately."""
    leaves: list[_Leaf] = []
    for name, info in model.model_fields.items():
        annotation = _unwrap(info.annotation)
        path = f"{prefix}{name}"
        if get_origin(annotation) is list:
            continue
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            leaves += _leaves(annotation, f"{path}.", chain + (name,))
        else:
            leaves.append(_Leaf(path, chain + (name,), _kind_of(annotation, path)))
    return leaves


def _list_leaves(model: type[BaseModel]) -> dict[str, list[_Leaf]]:
    """For each list field of the model, the scalar leaves of its entries (paths start `name[].`)."""
    lists: dict[str, list[_Leaf]] = {}
    for name, info in model.model_fields.items():
        annotation = _unwrap(info.annotation)
        if get_origin(annotation) is list:
            (element,) = get_args(annotation)
            lists[name] = _leaves(element, prefix=f"{name}[].")
    return lists


INVOICE_LEAVES: list[_Leaf] = _leaves(Invoice)
INVOICE_LISTS: dict[str, list[_Leaf]] = _list_leaves(Invoice)


def _get(obj: Any, chain: tuple[str, ...]) -> Any:
    for attribute in chain:
        obj = getattr(obj, attribute)
    return obj


# --- results -------------------------------------------------------------------------------------


class FieldResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    status: FieldStatus
    expected: str | None
    predicted: str | None


class ListResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    expected_count: int
    predicted_count: int
    correct_entries: int
    extra_entries: int
    missing_entries: int
    exact: bool
    # Same entries as the ground truth in another order: labelled apart from misread values (§3).
    order_only_mismatch: bool
    # Only the wrong fields of position-matched entries; paths look like `items[2].unit_price`.
    entry_errors: list[FieldResult]


class ComparisonResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    classification: Classification
    expected_outcome: ExpectedOutcome
    actual_outcome: ExpectedOutcome
    expected_reason: FailureReason | None
    actual_reason: FailureReason | None
    # Informative only (PRD 03 R3.4): set for correct rejections, never changes the classification.
    reason_agrees: bool | None
    # Scored only for extractions (§2 denominator); empty otherwise.
    fields: list[FieldResult]
    lists: list[ListResult]
    invented_values: int
    missed_values: int


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _field_result(path: str, leaf: _Leaf, expected: Any, predicted: Any) -> FieldResult:
    return FieldResult(
        path=path,
        status=compare_value(leaf.kind, expected, predicted),
        expected=_text(expected),
        predicted=_text(predicted),
    )


# --- lists (§3) ----------------------------------------------------------------------------------


def compare_list(name: str, predicted: list[Any], expected: list[Any], leaves: list[_Leaf]) -> ListResult:
    correct = 0
    errors: list[FieldResult] = []
    for index, (p_entry, e_entry) in enumerate(zip(predicted, expected)):
        wrong = [
            result
            for leaf in leaves
            if (
                result := _field_result(
                    leaf.path.replace("[]", f"[{index}]", 1),
                    leaf,
                    _get(e_entry, leaf.chain),
                    _get(p_entry, leaf.chain),
                )
            ).status
            != "correct"
        ]
        if wrong:
            errors += wrong
        else:
            correct += 1

    exact = len(predicted) == len(expected) and correct == len(expected)

    def key(entry: Any) -> tuple:
        return tuple(normalize(leaf.kind, _get(entry, leaf.chain)) for leaf in leaves)

    order_only = not exact and Counter(map(key, predicted)) == Counter(map(key, expected))
    return ListResult(
        name=name,
        expected_count=len(expected),
        predicted_count=len(predicted),
        correct_entries=correct,
        extra_entries=max(0, len(predicted) - len(expected)),
        missing_entries=max(0, len(expected) - len(predicted)),
        exact=exact,
        order_only_mismatch=order_only,
        entry_errors=errors,
    )


def compare_invoice(predicted: Invoice, expected: Invoice) -> tuple[list[FieldResult], list[ListResult]]:
    fields = [
        _field_result(leaf.path, leaf, _get(expected, leaf.chain), _get(predicted, leaf.chain))
        for leaf in INVOICE_LEAVES
    ]
    lists = [
        compare_list(name, getattr(predicted, name), getattr(expected, name), leaves)
        for name, leaves in INVOICE_LISTS.items()
    ]
    return fields, lists


# --- document outcome (§1) -----------------------------------------------------------------------

_CLASSIFICATION: dict[tuple[ExpectedOutcome, ExpectedOutcome], Classification] = {
    ("extracted", "extracted"): "extraction",
    ("extracted", "explicit_failure"): "false_rejection",
    ("explicit_failure", "extracted"): "false_acceptance",
    ("explicit_failure", "explicit_failure"): "correct_rejection",
}


def actual_outcome(prediction: ExtractionResult | None) -> ExpectedOutcome:
    """`None` is a call that produced no result (API error, truncation, refusal): an explicit failure."""
    return "extracted" if prediction is not None and isinstance(prediction.result, Extracted) else "explicit_failure"


def classify(expected: ExpectedOutcome, actual: ExpectedOutcome) -> Classification:
    return _CLASSIFICATION[(expected, actual)]


def compare(
    prediction: ExtractionResult | None,
    ground_truth: Invoice | None,
    expected_outcome: ExpectedOutcome,
    expected_reason: FailureReason | None,
) -> ComparisonResult:
    """Score one document. `prediction` is `None` when the call produced no result."""
    actual = actual_outcome(prediction)
    classification = classify(expected_outcome, actual)
    actual_reason = (
        prediction.result.reason if prediction is not None and isinstance(prediction.result, Failed) else None
    )

    fields: list[FieldResult] = []
    lists: list[ListResult] = []
    if classification == "extraction":
        if ground_truth is None:
            raise ValueError("an extracted document needs its ground-truth invoice to be scored")
        fields, lists = compare_invoice(prediction.result.invoice, ground_truth)

    scored = fields + [error for result in lists for error in result.entry_errors]
    return ComparisonResult(
        classification=classification,
        expected_outcome=expected_outcome,
        actual_outcome=actual,
        expected_reason=expected_reason,
        actual_reason=actual_reason,
        reason_agrees=(actual_reason == expected_reason) if classification == "correct_rejection" else None,
        fields=fields,
        lists=lists,
        invented_values=sum(r.status == "invented" for r in scored),
        missed_values=sum(r.status == "missed" for r in scored),
    )
