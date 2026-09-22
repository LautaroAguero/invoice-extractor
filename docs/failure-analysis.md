# Failure analysis: baseline run

Status: baseline · Run: `20260922-155901-path_a-148bac7` (path A) · Model: `claude-sonnet-5` · Prompt: `v1`

This is PRD 03 R6: every wrong field of the baseline run, classified, with one example each, ending in a ranked list of hypotheses for PRD 04. It covers path A, the ingestion path PRD 03 R5.4 names the winner (see [docs/quality-report.md](quality-report.md)); path B's own errors are a strict subset (see [Path B](#path-b-note)).

## Baseline numbers

30 synthetic documents, 25 in-domain, 5 negatives. Correct outcome 30/30 (100.0%, 95% CI [88.6, 100.0]). Zero false rejections, zero false acceptances, zero missed values. Field precision is 100% on every scored field except the two `items` list metrics (`items_exact` 24/25, `items_per_entry` 129/132), both caused by the single case below. Full numbers: [docs/quality-report.md](quality-report.md).

## Every wrong field, by category

| Category | Count | Documents |
|---|---|---|
| Invented value | 3 | B05 (all 3 `items[].vat_rate`) |
| Misread value | 0 | — |
| Column confusion | 0 | — |
| Wrong field chosen | 0 | — |
| Formatting | 0 | — |
| Rejection error | 0 | — |
| Order-only mismatch (lists) | 0 | — |

Every wrong field in this run falls into one category, on one document.

### Invented value — `items[].vat_rate` on B05

**What happened.** B05 is a Factura B (no VAT breakdown printed; the schema's `vat_rate` description says "null when the table has no 'IVA' column (Factura B and C)"). Ground truth has `vat_rate: null` on all 3 rows. The model returned `"0"` on all 3 rows instead of `null`.

```
                    ground truth    predicted
items[0].vat_rate   null            "0"
items[1].vat_rate   null            "0"
items[2].vat_rate   null            "0"
```

**Why it is "invented", not "wrong".** Per `docs/measurement-rules.md` §2, a non-null prediction where ground truth is `null` is scored wrong and counted as an invented value — the report's most dangerous error category (PRD 03 R2.3), because a consumer of this field cannot tell an invented `"0"` from a real 0% rate without checking the source document.

**Why it likely happened.** 10 of the 11 other Factura B/C documents in the dataset print no IVA column and the model correctly returned `null` for all of them (B01, B02, B04, B07, C01–C05). Two Factura B documents (B03, B06) do print a real IVA column with non-zero rates, and the model read those correctly too. B05 is the only document where the model substituted `0` for an absent column instead of `null` — not a systemic confusion between "no column" and "0%", since every other no-column case in the same run was handled correctly.

## Ranked hypotheses for PRD 04

1. **Add a negative example to the prompt for the null-vs-zero distinction on `vat_rate`.** *(Highest confidence — direct evidence.)* v1 has no examples by design (PRD 03 spec: "no examples or field-specific tuning"); this is exactly the kind of ambiguity an example resolves. Evidence: B05 above, one document, one field, no other Factura B/C document in the dataset shows the same failure — consistent with a boundary case an example would close rather than a rule the model doesn't know (it applied the rule correctly 10/11 times).
2. **Add a business-validation check that a Factura B/C invoice has no non-null `vat_rate`.** *(High confidence — deterministic, catches the class even if hypothesis 1 doesn't fully close it.)* PRD 00 CC-2 keeps this as a separate validation module, not a prompt change; it would have caught this exact case and gives PRD 04 a corrective-retry target with a precise error message. Evidence: the rule is fully determined by `invoice_type` (B and C never show a VAT breakdown), so it is a pure structural check, not a judgment call.
3. **Watch dense multi-line invoices for `items_per_entry` regressions before ruling out a broader pattern.** *(Lower confidence — one document is not enough to confirm or rule out a link to row count.)* B05 has only 3 rows, but `A04` (`dense_table`, more rows) scored perfectly in this run, which weighs against "more rows → more invented values." Evidence: with only one failing case, PRD 04 should re-check this after hypothesis 1 or 2 ships, using the per-tag breakdown in the report rather than assuming a pattern from n=1.

## Path B note

Path B's own run (`20260922-160125-path_b-148bac7`) has **zero** wrong fields: it also read B05's `vat_rate` as `null` on all 3 rows, correctly. Path B sends the document as plain extracted text rather than a rendered page, so B05's invented value is specific to path A's input representation for this one document — worth a note if hypothesis 1's example is added, since it suggests the ambiguity is more visual (the image contains no IVA column to point to) than textual.

Path B's failures are all coverage, not extraction quality: 4 documents it cannot read at all (`A05`, `C05`: no text layer; `A09`, `B07`: image only), each an explicit failure with no invented or missed value. See the ingestion path comparison in [docs/quality-report.md](quality-report.md) for the full paired result.
