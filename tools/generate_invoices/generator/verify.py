"""Field-by-field verification of ground truth against the rendered PDF text (design D2, tasks.md 4.3).

Every non-null leaf value of the ground truth `invoice` object must be found,
in its printed format, in the clean PDF's pdfplumber text (whitespace collapsed
on both sides). `currency` is skipped by convention when it is "ARS": the
template prints nothing for a peso invoice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import formatting as fmt


@dataclass
class Check:
    path: str
    printed_value: str | None  # None means "skipped"
    skip_reason: str | None = None
    match_mode: str = "substring"  # or "word_subsequence" (see description checks below)


@dataclass
class VerificationResult:
    passed: bool
    checked: int
    skipped: list[str]
    failed_field: str | None = None
    checks: list[Check] = field(default_factory=list)


def iter_checks(invoice: dict) -> list[Check]:
    checks: list[Check] = []

    def add(path: str, printed_value: str | None, skip_reason: str | None = None, match_mode: str = "substring") -> None:
        checks.append(Check(path=path, printed_value=printed_value, skip_reason=skip_reason, match_mode=match_mode))

    if invoice.get("document_code") is not None:
        add("document_code", fmt.format_document_code(invoice["document_code"]))
    add("point_of_sale", invoice["point_of_sale"])
    add("invoice_number", invoice["invoice_number"])
    add("issue_date", fmt.format_date(invoice["issue_date"]))
    if invoice.get("due_date") is not None:
        add("due_date", fmt.format_date(invoice["due_date"]))

    issuer = invoice["issuer"]
    add("issuer.name", issuer["name"])
    add("issuer.cuit", fmt.format_cuit(issuer["cuit"]))
    add("issuer.vat_condition", fmt.format_issuer_vat_condition(issuer["vat_condition"]))

    customer = invoice["customer"]
    if customer.get("name") is not None:
        add("customer.name", customer["name"])
    if customer.get("cuit") is not None:
        add("customer.cuit", fmt.format_cuit(customer["cuit"]))
    if customer.get("address") is not None:
        add("customer.address", customer["address"])
    add("customer.vat_condition", fmt.format_customer_vat_condition(customer["vat_condition"]))

    if invoice["currency"] == "ARS":
        add("currency", None, skip_reason="ARS is the not-printed convention")
    else:
        add("currency", fmt.format_currency(invoice["currency"]))
    if invoice.get("exchange_rate") is not None:
        add("exchange_rate", invoice["exchange_rate"])

    for i, item in enumerate(invoice["items"]):
        p = f"items[{i}]"
        if item.get("code") is not None:
            add(f"{p}.code", item["code"])
        # A description that wraps onto several lines can have the row's own
        # Cantidad value (single-line, anchored at the row's top) interleaved
        # after its first wrapped line by pdfplumber's reading order (confirmed
        # generating case A03, task 7.1) — a word-subsequence match tolerates
        # that without loosening the check for a truncated or altered word.
        add(f"{p}.description", item["description"], match_mode="word_subsequence")
        add(f"{p}.quantity", fmt.format_amount(item["quantity"]))
        add(f"{p}.unit_price", fmt.format_amount(item["unit_price"]))
        if item.get("discount") is not None:
            add(f"{p}.discount", fmt.format_amount(item["discount"]))
        if item.get("vat_rate") is not None:
            add(f"{p}.vat_rate", fmt.format_vat_rate(item["vat_rate"]))
        add(f"{p}.line_amount", fmt.format_amount(item["line_amount"]))

    for i, line in enumerate(invoice["vat_breakdown"]):
        add(f"vat_breakdown[{i}].rate", fmt.format_vat_rate(line["rate"]))
        add(f"vat_breakdown[{i}].amount", fmt.format_amount(line["amount"]))

    if invoice.get("net_amount") is not None:
        add("net_amount", fmt.format_amount(invoice["net_amount"]))
    if invoice.get("non_taxed_amount") is not None:
        add("non_taxed_amount", fmt.format_amount(invoice["non_taxed_amount"]))
    if invoice.get("exempt_amount") is not None:
        add("exempt_amount", fmt.format_amount(invoice["exempt_amount"]))
    # vat_amount is always null for this generator (design D3): never checked.

    add("total", fmt.format_amount(invoice["total"]))

    cae = invoice["cae"]
    add("cae.number", cae["number"])
    add("cae.expiry_date", fmt.format_date(cae["expiry_date"]))

    return checks


def _word_subsequence_found(haystack: str, needle: str) -> bool:
    """Every word of `needle` appears in `haystack`, in order, other words allowed
    in between. See the description check in `iter_checks` for why."""
    haystack_words = iter(haystack.split())
    return all(any(w == needle_word for w in haystack_words) for needle_word in needle.split())


def _vat_breakdown_in_printed_order(invoice: dict, haystack: str) -> bool:
    """Each "IVA <rate> <amount>" line appears after the previous one (design D4).

    Found values alone do not prove order: 148bac7 had to fix 4 ground truths whose
    lines were all printed, but listed in a different order than the document's.
    """
    position = -1
    for line in invoice["vat_breakdown"]:
        needle = f"IVA {fmt.format_vat_rate(line['rate'])} {fmt.format_amount(line['amount'])}"
        found = haystack.find(needle, position + 1)
        if found == -1:
            return False
        position = found
    return True


def verify_invoice(invoice: dict, pdf_text: str) -> VerificationResult:
    haystack = fmt.collapse_whitespace(pdf_text)
    checks = iter_checks(invoice)

    checked = 0
    skipped: list[str] = []
    failed_field: str | None = None
    for check in checks:
        if check.skip_reason is not None:
            skipped.append(check.path)
            continue
        checked += 1
        needle = fmt.collapse_whitespace(check.printed_value)
        found = _word_subsequence_found(haystack, needle) if check.match_mode == "word_subsequence" else needle in haystack
        if not found:
            failed_field = check.path
            break
    # Order is a property of the list, not a field: it fails generation but is not counted.
    if failed_field is None and not _vat_breakdown_in_printed_order(invoice, haystack):
        failed_field = "vat_breakdown"

    return VerificationResult(
        passed=failed_field is None,
        checked=checked,
        skipped=skipped,
        failed_field=failed_field,
        checks=checks,
    )
