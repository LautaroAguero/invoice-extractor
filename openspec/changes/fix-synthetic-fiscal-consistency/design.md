## Context

See proposal.md for the three defects. Facts about the generator that shape the fix:

- `generate_params` draws, per item, a quantity, a unit price (`randint(500, 1500) * 100`) and a VAT rate (`rng.choice(VAT_RATES)`), and then the CAE, from one seeded `random.Random`. `Item.line_amount` is net, `Item.vat_amount` is computed from it, and `InvoiceParams.total` is net + VAT for every letter.
- `render.py` passes `importe = line_amount` and `imp_total = net + VAT` to pyfepdf for every letter. pyfepdf prints item prices and amounts as given. On B and C it prints no NETO and no per-rate IVA lines, and on B it prints the rate column only for a consumidor final (`pyfepdf.py:1325-1340`). The issuer header string is fixed to "IVA Responsable Inscripto".
- pyfepdf prints each VAT line at a fixed template position (`IVA2.5`, `IVA5`, `IVA10.5`, `IVA21`, `IVA27` at increasing y in `qr_base.csv`), so the printed order is the template's, not the insertion order. `visibility.py` writes `params.vat_breakdown` in first-seen order, which is why A03/A04/A07/A10 were hand-corrected in `148bac7`.
- Reproducibility is a spec contract: same seed gives byte-identical ground truth and PDFs, and generation refuses to run with uncommitted generator code.

## Goals / Non-Goals

**Goals:**
- B and C documents a reader can check from the print alone, and a Factura C that is fiscally coherent.
- A generator that reproduces the committed ground truth exactly, including the four hand-corrected A files.
- A, E and the four unaffected negatives unchanged to the byte, so their review stamps and the evaluation history about them stay valid.

**Non-Goals:**
- An "IVA Contenido" line on B (the templates have no field for it; PRD 02 decision stands).
- A new layout, new cases, or changes to degradation.
- Re-running path B or the path comparison.

## Decisions

### D1. Factura B: the drawn price is the VAT-included price

The random draws are unchanged: the drawn unit price is read as the gross price for B. `Item` gets `vat_included: bool`, set from a per-letter `pricing` argument of `generate_params`: `"net"` for A, `"gross"` for B (including the nota de débito B), and `"none"` for C and E.

For a gross item:
- `line_amount` = qty × price − discount (printed, VAT included)
- `net_amount` = `(line_amount / (1 + rate/100)).quantize(CENT, ROUND_HALF_UP)`
- `vat_amount` = `line_amount − net_amount`

So net + VAT equals the printed line exactly, with no rounding drift. The invoice's net and VAT are the sums over items. Its total is the sum of printed lines. Per-rate bases and amounts for `AgregarIva` come from the item nets and VATs. `render.py` passes these to pyfepdf as `imp_neto`, `imp_iva` and `imp_total`, which is what WSFE expects for a B.

Alternative: draw a net price and compute a gross price from it. Rejected: it produces odd-cent unit prices, changes the draw sequence, and would change every A document's CAE and later values too.

### D2. Factura C and E: no VAT

With pricing `"none"`, the rate is still drawn to keep the sequence, then discarded (`vat_rate = None`). E already draws `Decimal("0")` for foreign currency; normalizing it to `None` changes no printed value, and ground truth already has `vat_rate: null` for E. For C, `imp_neto` = total and `imp_iva` = 0.

The C issuer label becomes "Responsable Monotributo": it prints as "IVA Responsable Monotributo" in the header, and the ground truth `issuer.vat_condition` is `responsable_monotributo`. The issuer label moves from a module constant to a per-letter function used by both `render.py` and `visibility.py`, so the print and the ground truth cannot disagree.

### D3. `vat_breakdown` order comes from the template

`visibility.py` orders the breakdown by the y coordinate of the `IVA<rate>` field in the case's template CSV. It is read once per template, and ties are broken by x. `qr_variant` only moves item columns, but it is read on its own rather than assumed identical. A rate with no template field fails generation, which cannot happen with the current rates (10.5 and 21).

Alternative: sort by rate. Rejected: correct by coincidence for these templates only.

### D4. Verification checks the order

`verify.py` finds each `vat_breakdown` entry's printed label ("I.V.A. 10,5%") in the clean text layer and asserts the positions increase in ground-truth order. A failure names `vat_breakdown`. A test feeds a reversed breakdown and asserts generation fails, reproducing the `148bac7` defect.

### D5. Regeneration and review

1. Commit the generator changes (generation refuses dirty code).
2. Run `generate_dataset` into a temporary directory.
3. A comparison script lists every file that differs from `ground_truth/`, and it must list exactly: B01–B07 and C01–C05 (`.json` plus `.pdf`/`.jpg`) and `nota_debito_b.pdf`. Any other difference stops the change.
4. Copy the new files in. In `manifest.jsonl`, every entry takes the new `generator_version`; `gt_check` and `pages` are refreshed; `reviewed_by`/`reviewed_at` are reset to null for the 16 changed documents only.
5. The user reviews those 16 with the existing `review` checklist command (the spec's human review requirement), which stamps them.

`test_regeneration.py` then passes on the committed dataset. That is the first time since `148bac7`.

### D6. Re-run baseline and historical runs

One path A run with the stage 3 command: `python -m invoice_extractor.evaluate --path a --spend-cap 3`.

**Model call site:** unchanged from stage 3 (`ModelClient.call` through `extract_path_a`). API errors, timeouts and rate limits are retried by the SDK up to `max_retries`, then become an `api_error` document outcome. Truncated, refused and invalid output are typed failures, recorded as that document's outcome. Auth and unknown-model errors abort the run. Nothing new is introduced.

**Estimated** (until measured): the same tokens per document as the stage 3 run, since B/C prices differ only in value. So about $0.038 per document, $1.1–1.3 per run, and p95 about 45s.

The stage 3 records (`20260922-155901-path_a-148bac7`, `20260922-160125-path_b-148bac7`) stay in `runs/`, untouched. They carry generator SHA `f7ff2e1` and the new run carries the new one. `docs/quality-report.md` is re-rendered from the new run, and its path comparison section is kept with a note saying it was measured on the previous dataset version. `docs/failure-analysis.md` is rewritten on the new run, keeping the planning finding that hypothesis 2 is contradicted by B03/B06. Stage 4's version comparison must refuse run records whose manifests carry different generator versions (added to `add-validation-and-iterations` design D5).

## Risks / Trade-offs

- [Changing the B pricing rule shifts the random sequence and silently changes A/E] → D1/D2 keep every draw. D5 step 3 treats any change outside the 16 expected documents as a stop condition.
- [A B03/B06 line now prints a VAT-included amount next to a rate, which the model might read as net] → This is how a real B to a consumidor final looks. The baseline re-run measures it, and it is exactly the kind of evidence stage 4 needs.
- [ROUND_HALF_UP on the net per line breaks V4-style checks on B] → B prints no breakdown, so V4 does not run on B. The unprinted net and VAT still add up exactly (D1).
- [The new baseline differs from the stage 3 numbers and makes stage 3 look inconsistent] → Stage 3 records are kept and labeled with their dataset version. The quality report says which dataset each section measured.
- [A Factura C issuer "Tecnored Patagonia S.A." with a 30- CUIT cannot really be a monotributista (only natural persons can)] → Accepted and documented (user decision, 2026-09-22). A natural-person name and a 20/23/27 CUIT would break the spec rule that keeps synthetic CUITs off natural-person prefixes, so a generated CUIT can never match a real person. The coherence that the validator and the model depend on (a C has no VAT and prints "IVA Responsable Monotributo") holds.
- [16 documents need a human review again] → The review command already exists, and the checklist shows the null fields. That is roughly 20 minutes of the user's time, and the task is theirs.
