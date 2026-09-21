# Quality report

Run: claude-sonnet-5 | prompt v1 | path a | b8bc5d4 | 2026-09-17T12:00:00Z

## Documents

8 documents (in-domain 5, negatives 3).

| Measure | n | % | 95% CI | |
|---|---|---|---|---|
| Correct outcome | 6/8 | 75.0% | [40.9, 92.9] | |
| Extraction rate (of in-domain) | 4/5 | 80.0% | [37.6, 96.4] | |
| Reason agreement (correct rejections) | 1/2 | 50.0% | [9.5, 90.5] | informative, not scored |

False rejections: 1. Correct rejections: 2. False acceptances: 1. Invented values: 1. Missed values: 1.

## Field precision (over successful extractions: 4)

| Field | n/N | % | 95% CI | |
|---|---|---|---|---|
| `invoice_type` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `document_code` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `point_of_sale` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `invoice_number` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `issue_date` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `due_date` | 3/4 | 75.0% | [30.1, 95.4] | **worst field** |
| `issuer.name` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `issuer.cuit` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `issuer.vat_condition` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `customer.name` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `customer.cuit` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `customer.address` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `customer.vat_condition` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `currency` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `exchange_rate` | 3/4 | 75.0% | [30.1, 95.4] |  |
| `net_amount` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `non_taxed_amount` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `exempt_amount` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `vat_amount` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `total` | 3/4 | 75.0% | [30.1, 95.4] |  |
| `cae.number` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `cae.expiry_date` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `items_exact` | 3/4 | 75.0% | [30.1, 95.4] |  |
| `items_per_entry` | 15/16 | 93.8% | [71.7, 98.9] | extra entries 0 |
| `vat_breakdown_exact` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `vat_breakdown_per_entry` | 8/8 | 100.0% | [67.6, 100.0] | extra entries 0 |
| `other_taxes_exact` | 4/4 | 100.0% | [51.0, 100.0] |  |
| `other_taxes_per_entry` | 0/0 | n/a |  | extra entries 0 |

Worst field: `due_date`

## By tag

| Tag | Documents | Correct outcome | 95% CI | Perfect extractions | 95% CI |
|---|---|---|---|---|---|
| dense_table | 1 | 1/1 | [20.7, 100.0] | 0/1 | [0.0, 79.3] |
| foreign_currency | 1 | 1/1 | [20.7, 100.0] | 0/1 | [0.0, 79.3] |
| multi_page | 1 | 1/1 | [20.7, 100.0] | 0/1 | [0.0, 79.3] |
| not_an_invoice | 2 | 1/2 | [9.5, 90.5] | 0/0 |  |
| skewed_scan | 1 | 0/1 | [0.0, 79.3] | 0/0 |  |
| unsupported_document | 1 | 1/1 | [20.7, 100.0] | 0/0 |  |
| (no tag) | 1 | 1/1 | [20.7, 100.0] | 1/1 | [20.7, 100.0] |

## Attempts, cost and latency

Attempts: 1: 8, 2: 0, 3: 0

Cost (measured from usage): total $0.0690, mean $0.0086 per document.

Latency (wall clock per document): p50 1.5s, p95 4.0s.

## Real set (2 documents)

**Not a headline number.** Too small for a confidence interval, and never mixed into any number above.

Extractions 1/2, false rejections 1, cost $0.0300.

Field precision (over successful extractions: 1):

| Field | n/N | % | 95% CI | |
|---|---|---|---|---|
| `invoice_type` | 1/1 | 100.0% |  |  |
| `document_code` | 1/1 | 100.0% |  |  |
| `point_of_sale` | 1/1 | 100.0% |  |  |
| `invoice_number` | 1/1 | 100.0% |  |  |
| `issue_date` | 1/1 | 100.0% |  |  |
| `due_date` | 1/1 | 100.0% |  |  |
| `issuer.name` | 1/1 | 100.0% |  |  |
| `issuer.cuit` | 1/1 | 100.0% |  |  |
| `issuer.vat_condition` | 1/1 | 100.0% |  |  |
| `customer.name` | 1/1 | 100.0% |  |  |
| `customer.cuit` | 1/1 | 100.0% |  |  |
| `customer.address` | 1/1 | 100.0% |  |  |
| `customer.vat_condition` | 1/1 | 100.0% |  |  |
| `currency` | 1/1 | 100.0% |  |  |
| `exchange_rate` | 1/1 | 100.0% |  |  |
| `net_amount` | 1/1 | 100.0% |  |  |
| `non_taxed_amount` | 1/1 | 100.0% |  |  |
| `exempt_amount` | 1/1 | 100.0% |  |  |
| `vat_amount` | 1/1 | 100.0% |  |  |
| `total` | 1/1 | 100.0% |  |  |
| `cae.number` | 1/1 | 100.0% |  |  |
| `cae.expiry_date` | 1/1 | 100.0% |  |  |
| `items_exact` | 1/1 | 100.0% |  |  |
| `items_per_entry` | 4/4 | 100.0% |  | extra entries 0 |
| `vat_breakdown_exact` | 1/1 | 100.0% |  |  |
| `vat_breakdown_per_entry` | 2/2 | 100.0% |  | extra entries 0 |
| `other_taxes_exact` | 1/1 | 100.0% |  |  |
| `other_taxes_per_entry` | 0/0 | n/a |  | extra entries 0 |
