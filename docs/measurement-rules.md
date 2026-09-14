# Measurement rules

Status: decided 2026-09-14 · Resolves OQ-1 (PRD 03)

These rules are fixed **before** the first baseline run. Changing them later requires a new entry in the change log at the bottom and re-rendering every reported run with the new rules. Runs scored under different rules are never compared.

## 1. Documents and outcomes

Every document in the manifest has an `expected_outcome`:

- `extracted`: an in-domain invoice.
- `explicit_failure`: a `not_an_invoice` negative.

Every run produces one actual outcome per document: `extracted` (a schema-valid object that passed business validation, when validation exists) or `explicit_failure` (the model's failure outcome, validation still failing after the last attempt, truncation, refusal, or an unrecoverable API error).

| Expected \ Actual | extracted | explicit_failure |
|---|---|---|
| `extracted` | extraction | **false rejection** |
| `explicit_failure` | **false acceptance** (invented invoice) | correct rejection |

**Correct outcome rate (headline)** = (extractions + correct rejections) / all documents. *(Decision 1a)*

The report also shows, as separate lines, the counts of false rejections, false acceptances and correct rejections. A false acceptance is the worst document-level error and is always shown, even when it is 0.

## 2. Field precision

**Denominator:** in-domain documents whose actual outcome is `extracted`. *(Decision 4b)*

The field-precision block is **always printed together with the extraction rate over in-domain documents**. Field precision alone hides failures: a system that fails more often can show higher field precision. The n of every field line makes the denominator visible (for example `24/28`).

**Scored fields:** every leaf field of the result schema, with nested fields flattened (`issuer.cuit`, `cae.expiry_date`). Items are scored separately (§3).

**A field is correct when** its normalized prediction equals its normalized ground truth (§4). For optional fields:

| Ground truth | Prediction | Result |
|---|---|---|
| value | same value | correct |
| value | different value | wrong |
| value | `null` | wrong, also counted as **missed value** |
| `null` | `null` | correct *(Decision 2a)* |
| `null` | value | wrong, also counted as **invented value** |

Consequence of 2a: optional fields that are usually absent score high by returning `null`. The **invented values** and **missed values** counts are always reported, next to field precision, to keep that visible.

## 3. Items *(Decision 3c: both metrics)*

Items are matched **by position**: predicted item *i* against ground-truth item *i*, in document order. An item is correct when every one of its fields is correct under §2 and §4.

- **items_exact** (document level): the predicted list has the same length as the ground truth and every item is correct. Denominator: same as field precision.
- **items_per_item** (item level): correct items / ground-truth items, summed over the documents in the field-precision denominator. Extra predicted items beyond the ground-truth length are reported as a separate **extra items** count.

Position matching means one skipped row makes every following item wrong. That is intended (a skipped row is a real extraction error), but if the failure analysis shows shift cascades dominating, matching by description is the first rule to reconsider, through the change log.

## 4. Normalization and equality

| Kind | Rule |
|---|---|
| Amounts, quantities, rates, exchange rate | Parsed to `Decimal`, compared **exactly** by numeric value (`150000.00 == 150000`). No tolerance. *(Decision 5a)* |
| Dates | ISO `YYYY-MM-DD`, exact |
| CUIT | Digits only, exact |
| Point of sale, invoice number, CAE | Digits only, leading zeros preserved, exact |
| Enums | Exact value |
| Free text (names, addresses, descriptions) | Unicode NFC, casefold, collapse whitespace, strip; otherwise exact |

Normalization is implemented once and unit-tested. Exact amount comparison applies to **measurement only**; business validation (PRD 04) has its own rounding rules for cross-field sums.

## 5. Attempts, cost, latency

- **Attempts:** corrective attempts per document (1 = no retry). Transport retries are recorded separately and not counted here.
- **Cost:** sum over every model call made for the document, computed from `usage` with the price table in effect at run time.
- **Latency:** wall clock per document from the start of the first call to the final outcome, retries included. The report shows p50 and p95.

## 6. Statistics

- Every rate is reported with its n and a 95% Wilson interval.
- Comparisons between versions run on the same documents and use a paired test (McNemar exact) on per-document correct outcome, plus per-field deltas.
- Incomplete runs (spend cap reached) are never reported as results.

## Change log

| Date | Change | Reason |
|---|---|---|
| 2026-09-14 | Initial rules (decisions 1a, 2a, 3c, 4b, 5a) | — |
