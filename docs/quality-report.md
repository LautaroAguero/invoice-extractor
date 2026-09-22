# Quality report

Run: claude-sonnet-5 | prompt v1 | path a | 148bac7 | 2026-09-22T15:59:01Z

## Documents

30 documents (in-domain 25, negatives 5).

| Measure | n | % | 95% CI | |
|---|---|---|---|---|
| Correct outcome | 30/30 | 100.0% | [88.6, 100.0] | |
| Extraction rate (of in-domain) | 25/25 | 100.0% | [86.7, 100.0] | |
| Reason agreement (correct rejections) | 5/5 | 100.0% | [56.6, 100.0] | informative, not scored |

False rejections: 0. Correct rejections: 5. False acceptances: 0. Invented values: 3. Missed values: 0.

## Field precision (over successful extractions: 25)

| Field | n/N | % | 95% CI | |
|---|---|---|---|---|
| `invoice_type` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `document_code` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `point_of_sale` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `invoice_number` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `issue_date` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `due_date` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `issuer.name` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `issuer.cuit` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `issuer.vat_condition` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `customer.name` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `customer.cuit` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `customer.address` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `customer.vat_condition` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `currency` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `exchange_rate` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `net_amount` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `non_taxed_amount` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `exempt_amount` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `vat_amount` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `total` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `cae.number` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `cae.expiry_date` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `items_exact` | 24/25 | 96.0% | [80.5, 99.3] |  |
| `items_per_entry` | 129/132 | 97.7% | [93.5, 99.2] | extra entries 0, **worst field** |
| `vat_breakdown_exact` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `vat_breakdown_per_entry` | 19/19 | 100.0% | [83.2, 100.0] | extra entries 0 |
| `other_taxes_exact` | 25/25 | 100.0% | [86.7, 100.0] |  |
| `other_taxes_per_entry` | 0/0 | n/a |  | extra entries 0 |

Worst field: `items_per_entry`

## By tag

| Tag | Documents | Correct outcome | 95% CI | Perfect extractions | 95% CI |
|---|---|---|---|---|---|
| dense_table | 1 | 1/1 | [20.7, 100.0] | 1/1 | [20.7, 100.0] |
| foreign_currency | 3 | 3/3 | [43.9, 100.0] | 3/3 | [43.9, 100.0] |
| image_input | 2 | 2/2 | [34.2, 100.0] | 2/2 | [34.2, 100.0] |
| missing_optional | 3 | 3/3 | [43.9, 100.0] | 3/3 | [43.9, 100.0] |
| multi_page | 2 | 2/2 | [34.2, 100.0] | 2/2 | [34.2, 100.0] |
| not_an_invoice | 2 | 2/2 | [34.2, 100.0] | 0/0 |  |
| skewed_scan | 2 | 2/2 | [34.2, 100.0] | 2/2 | [34.2, 100.0] |
| unsupported_document | 3 | 3/3 | [43.9, 100.0] | 0/0 |  |
| (no tag) | 12 | 12/12 | [75.8, 100.0] | 11/12 | [64.6, 98.5] |

## Attempts, cost and latency

Attempts: 1: 30, 2: 0, 3: 0

Cost (measured from usage): total $1.1287, mean $0.0376 per document.

Latency (wall clock per document): p50 12.3s, p95 44.4s.

# Ingestion path comparison

30 documents. Path A sends the file as a document or image block; path B sends the text layer extracted locally with pdfplumber (no OCR).

| | Path A | Path B |
|---|---|---|
| Correct outcome | 30/30 (100.0%) | 26/30 (86.7%) |
| Extraction rate | 25/25 (100.0%) | 21/25 (84.0%) |
| Invented values | 3 | 0 |
| Cost per document | $0.0376 | $0.0300 |
| p95 latency | 44.4s | 42.1s |

## Coverage: 4 documents path B cannot read

These measure coverage, not extraction quality, so they are kept out of the paired test.

| Document | Why | Path A outcome | Tags |
|---|---|---|---|
| A05 | no_text_layer | extraction | skewed_scan |
| A09 | image_input | extraction | image_input |
| B07 | image_input | extraction | image_input |
| C05 | no_text_layer | extraction | skewed_scan |

## Paired result (26 documents both paths attempted)

Only A correct: 0. Only B correct: 0. McNemar exact p = 1.000.

## Field deltas (B minus A, points, over the 21 documents both paths extracted)

| Field | A | B | Delta |
|---|---|---|---|
| `invoice_type` | 21/21 | 21/21 | +0.0 |
| `document_code` | 21/21 | 21/21 | +0.0 |
| `point_of_sale` | 21/21 | 21/21 | +0.0 |
| `invoice_number` | 21/21 | 21/21 | +0.0 |
| `issue_date` | 21/21 | 21/21 | +0.0 |
| `due_date` | 21/21 | 21/21 | +0.0 |
| `issuer.name` | 21/21 | 21/21 | +0.0 |
| `issuer.cuit` | 21/21 | 21/21 | +0.0 |
| `issuer.vat_condition` | 21/21 | 21/21 | +0.0 |
| `customer.name` | 21/21 | 21/21 | +0.0 |
| `customer.cuit` | 21/21 | 21/21 | +0.0 |
| `customer.address` | 21/21 | 21/21 | +0.0 |
| `customer.vat_condition` | 21/21 | 21/21 | +0.0 |
| `currency` | 21/21 | 21/21 | +0.0 |
| `exchange_rate` | 21/21 | 21/21 | +0.0 |
| `net_amount` | 21/21 | 21/21 | +0.0 |
| `non_taxed_amount` | 21/21 | 21/21 | +0.0 |
| `exempt_amount` | 21/21 | 21/21 | +0.0 |
| `vat_amount` | 21/21 | 21/21 | +0.0 |
| `total` | 21/21 | 21/21 | +0.0 |
| `cae.number` | 21/21 | 21/21 | +0.0 |
| `cae.expiry_date` | 21/21 | 21/21 | +0.0 |
| `items_exact` | 20/21 | 21/21 | +4.8 |
| `items_per_entry` | 117/120 | 120/120 | +2.5 |
| `vat_breakdown_exact` | 21/21 | 21/21 | +0.0 |
| `vat_breakdown_per_entry` | 15/15 | 15/15 | +0.0 |
| `other_taxes_exact` | 21/21 | 21/21 | +0.0 |
| `other_taxes_per_entry` | 0/0 | 0/0 | n/a |

## Winner

**Path A.** Path A wins: 30/30 correct outcomes against 26/30 for path B. Cost per document is $0.0376 against $0.0300. The p95 latency is 44.4s against 42.1s. Path B cannot read 4 of 30 documents (no text layer or an image), so it fails them. On the documents both paths attempted the difference is within the noise (McNemar exact p = 1.000).
