## Context

See proposal.md (Why) for motivation and `specs/invoice-dataset/spec.md` for the requirements.

**Current state:**
- `tools/generate_invoices/spike_factura_a.py` renders one hard-coded Factura A, or a nota de crédito/débito A through `--tipo-cbte`.
- It runs on the pinned pyafipws commit `d595b07` in its own venv, with the Python 3.14 shims recorded in `requirements.txt`.
- The stage 1 schema and the hand-built fixture `tests/fixtures/spike_factura_a.extraction.json` fix the ground-truth conventions: printed zeros are values (`"0.00"`), not `null`; `currency` is `ARS` when nothing is printed.

**Constraints found by reading pyfepdf** (`pyafipws/pyfepdf.py` at the pinned commit) that shape this design:
- The template `factura.csv` has no fields for currency or exchange rate, although `ProcesarPlantilla` fills `moneda_ds`/`moneda_ctz` when a template defines them (`:1280-1288`).
- What is printed depends on the letter: `NETO` and per-rate IVA lines only for A/M (`:1454-1474`); no item VAT column for C/E (`:1477`); item VAT rate on B only when the customer category contains "CONS…FINAL" or "EXENTO" (`:1184`, `:1327`).
- On multi-page documents, totals print only on the last page, and every earlier page prints a running "Subtotal:" in the total box (`:1497-1528`).
- `fpdf` writes `CreationDate` from `datetime.now()` (`fpdf/fpdf.py:1606`), so PDFs differ on every run.
- pyfepdf swallows exceptions unless `LanzarExcepciones = True`.

This change makes no model calls. Tokens per call, cost per document and latency do not apply, and no model call site is added or changed.

## Goals / Non-Goals

**Goals:**
- A single generation command that produces the 30 documents, their ground truth and the manifest from a declared case list.
- The ground truth of every in-domain document is verified against its rendered print before it is written.
- Every document can be regenerated from the manifest alone.

**Non-Goals:**
- Any change to `src/`: image ingestion, the text path and the runner belong to the stage 3 change.
- A general-purpose invoice generator. Parameters cover only what the 30 cases need.
- Rendering real-world ticket formats. The real set is photographed, not generated.
- Verifying that a value is printed **in the right place**. That is what human review is for (D2).

## Decisions

### D1 · Change boundary: `tools/` and `ground_truth/` only

The generator, templates, degradation and verification live in `tools/generate_invoices/`. Outputs go to `ground_truth/`. The real set goes to the git-ignored `ground_truth_real/`.

- Keeping `src/` untouched makes the boundary checkable: a diff that touches `src/` means scope leaked.
- It also keeps the GPL-3.0 generator physically separate from the extractor package.
- Alternative considered: adding JPG ingestion here, so the real tickets can run early. Rejected because it splits ingestion across two changes. Stage 3 owns both image blocks and the text path (PRD 03 R5.1).

### D2 · Ground truth from parameters plus a visibility map, verified against the print

Pipeline per in-domain document:

```
case (seed, kind, letter, layout, tags)
   |
   v
parameters (seeded: parties, items, rates, dates, amounts; exact decimals)
   |
   +--> render clean PDF (pyfepdf, LanzarExcepciones=True, pinned CreationDate)
   |
   +--> ground truth = visibility_map(letter, customer category, pages)(parameters)
   |
   v
verify: for every non-null leaf, printed_format(value) in text(clean PDF)
   |          fail -> abort document, name the field, write nothing
   v
write PDF + ground truth JSON + manifest entry (gt_check recorded)
```

Printed formats come from the same formatting rules pyfepdf uses:
- **Amounts:** `.` as thousands separator and `,` for decimals.
- **Dates:** `DD/MM/YYYY`.
- **Identifiers:** CUIT as `NN-NNNNNNNN-N`; point of sale and number as `NNNNN-NNNNNNNN`; document code as `COD.NN`.
- **VAT rate:** `21%` or `10,5%`.
- **VAT condition:** its printed label.
- **Description:** as printed.

Text comes from pdfplumber's default `extract_text()` over all pages, the same library chosen for the stage 3 text path. Before the substring match, whitespace is collapsed on both sides, because pyfepdf may wrap descriptions onto several lines.

**Alternatives considered:**
- Parse ground truth from the PDF text. Rejected: circular, fragile on tables, and impossible for degraded documents.
- Hand annotation of 30 documents. Rejected as the primary method: the parameters already hold the truth, so the risk is the parameter-to-print mapping, which the check targets directly. Hand annotation stays for the real set (D10).
- Check only key values (the original PRD 02 R5.2). Rejected: truncated descriptions and fields that a letter does not print, the most likely mistakes, are not key values.

**Known blind spots**, covered by human review (spec: human review of every document):
- **Common strings match anywhere.** "0,00" appears many times, so a zero in the wrong cell still "passes".
- **A `null` that is actually printed is not detected.** The check only proves that non-null values appear.

### D3 · Visibility map

Derived from the pyfepdf source at the pinned commit. Task 2 confirms each letter on its first render before the map is trusted.

| Ground-truth field | A | B | C | E |
|---|---|---|---|---|
| `net_amount` | printed ("Neto") | `null` | `null` | `null` |
| `vat_breakdown` | one line per rate | `[]` | `[]` | `[]` |
| `vat_amount` | `null` (only per-rate lines are printed) | `null` | `null` | `null` |
| `items[].vat_rate` | printed | printed only if customer is consumidor final or exento, else `null` | `null` | `null` |
| `items[].discount` | printed (the generator always sets a unit of measure, so "Bonif." prints even when zero, `:1040`) | same | same | same |
| `non_taxed_amount`, `exempt_amount` | printed, zero allowed | printed | printed | printed |
| `currency`, `exchange_rate` | `ARS` by convention, `null` | same | same | printed after D8, e.g. `USD` and the rate |
| `document_code` | printed (`COD.NN`) | printed | printed | printed |
| `customer.name/cuit/address` | printed | `null` when the case is a consumidor final without identification | printed or `null` per case | printed |
| totals on multi-page | last page only | same | same | same |

"IVA Contenido" (Ley 27.743) is not printed on B because the template has no field for it (decision (a) in exploration). The printed item rate on B for a consumidor final is kept in the ground truth, because it is visible.

### D4 · Two layouts

- **`qr_base`:** upstream `plantillas/factura_qr.csv` at the pinned commit, copied into `templates/` with the same edits the spike applies (no pyafipws logo, image paths made local). QR is the current ARCA format (RG 4892/2020); the barcode template stays only as the spike's reference.
- **`qr_variant`:** a copy of `qr_base` with different item-table labels ("Cant.", "P. Unit.", "Importe Neto" style) and the unit price and line amount columns swapped.

Field names do not change, so the visibility map (D3) and the verification (D2) are shared by both layouts. Only coordinates and label texts differ.

The variant deliberately departs from the literal labels quoted in the schema descriptions ("Precio", "Cantidad"). If extraction depends on those labels, stage 3 will show it as a per-layout difference.

- **Alternative:** 3 layouts (PRD 02 R1.5), adding a moved header block. Rejected for this change: it adds editing time and little diagnostic value at n=30. It becomes a measured PRD 04 lever if stage 3 shows layout-dependent errors.

### D5 · Negatives

Rendered by the same engine and templates, so they differ from invoices only where the real document differs. This makes them hard negatives.

| Negative | How | Printed letter | Expected reason |
|---|---|---|---|
| Nota de crédito A | `tipo_cbte` 3 | A | `unsupported_document_type` |
| Nota de débito B | `tipo_cbte` 7 | B | `unsupported_document_type` |
| Recibo | `tipo_cbte` 4 ("Recibo", letter A) | A | `unsupported_document_type` |
| Remito | `tipo_cbte` 91 ("Remito", letter R) | R | `not_an_invoice` |
| Presupuesto | Third template derived from `qr_base`: title "Presupuesto", no CAE, QR or barcode, legend "Documento no válido como factura" | none | `not_an_invoice` |

Negatives skip the field-by-field check, because their ground truth has no invoice. Their manifest `gt_check` is `null`, and review confirms the printed title.

### D6 · Reproducibility

- **Clean PDFs.** The generator fixes `fpdf`'s creation timestamp to a date derived from the case. The simplest pinning mechanism in the generator decides how: a subclass or a patch of the timestamp call. Nothing else in `fpdf` output depends on time or randomness; task 3 confirms it by rendering twice and comparing bytes.
- **Degraded PDFs.** Pillow's PDF writer receives fixed `creationDate` and `modDate` values.
- **Randomness.** One `random.Random(seed)` per case drives every random choice: parameters, rotation angle and sign, noise. Pillow's `effect_noise` is not seedable and is not used.
- **Contract tiers** (spec: reproducible generation). Ground truth and clean PDFs are byte-identical. Degraded documents are pixel-identical under the recorded Pillow, pypdfium2 and libjpeg versions, because JPEG bytes can differ across libjpeg builds.
- **Recorded:** `generator_version` records git SHA, pyafipws commit, fpdf, Pillow, pypdfium2 and pdfplumber versions.

### D7 · Degradation

Only for the 4 degraded cases, starting from the verified clean PDF.

1. **Rasterize** each page with pypdfium2 at 200 dpi.
2. **Rotate** by an angle in ±[2°, 5°], with white fill and canvas expanded.
3. **Add grayscale noise** from the case RNG, low amplitude, plus a light blur. The exact parameters are chosen on the first render so the text stays human-readable, then frozen and recorded.
4. **Save:**
   - `skewed_scan`: Pillow PDF, one image per page, no text layer. Verified by extracting text and getting an empty result.
   - `image_input`: JPEG quality 70, single page.

JPG cases are therefore single-page invoices.

- **Alternative:** no noise, only rotation, blur and JPEG artifacts. Rejected because it looks too clean to count as a scan.

### D8 · Currency fields in both layouts

Add `moneda.L`, `moneda_id`/`moneda_ds`, `moneda_ctz.L` and `moneda_ctz` fields to both layouts, the names `ProcesarPlantilla` fills.

E cases use `moneda_id` `DOL` (printed "USD: Dólar") or `060` ("EUR: Euro"), with a printed exchange rate. Ground truth is `currency` `USD`/`EUR` and `exchange_rate` as printed. For peso invoices the template leaves the fields empty, so `currency` stays `ARS` by convention and is skipped in verification.

### D9 · Manifest and case list

- **Case list.** `tools/generate_invoices/cases.py` declares the 30 cases: id, seed, kind, letter, layout, tags, and flags like consumidor final, pages and currency. The generator reads nothing else. Seeds are `1001`–`1030` in id order. Prompt example seeds (PRD 04) use `9000+`, disjoint by construction.
- **Manifest.** Written by the generator, except `reviewed_by`/`reviewed_at`. Those are filled after review, through a generator subcommand that records a review. Hand edits of JSONL are error-prone.
- **Aggregation check.** A composition check (counts per kind, letter and layout; required tags; 4 degraded; 15/15 split) runs after generation and fails when the manifest does not match the spec composition.

Assignment of tags to cases (fixed in `cases.py`):

| Letter / kind | Count | qr_base / qr_variant | Tags |
|---|---|---|---|
| A | 10 | 5 / 5 | `multi_page` ×1, `dense_table` ×1, `skewed_scan` ×1, `image_input` ×1 |
| B | 7 | 4 / 3 | `missing_optional` ×2 (consumidor final without identification), `multi_page` ×1, `image_input` ×1 |
| C | 5 | 2 / 3 | `missing_optional` ×1 (no due date), `skewed_scan` ×1 |
| E | 3 | 2 / 1 | `foreign_currency` ×3 (USD ×2, EUR ×1) |
| Negatives | 5 | 2 / 3 | `not_an_invoice` ×2, `unsupported_document` ×3 |

That totals 15 / 15. The JPG cases are single-page (D7), so `multi_page` and `image_input` never share a case.

### D10 · Real set

- **Location.** `ground_truth_real/` is added to `.gitignore` before any file is placed there. It gets a manifest with the same format: `source` `real`, and `null` for seed, generator version, degradation and `gt_check`.
- **Annotation.** Ground truth is written by hand against the photo, under the same visibility rule. It is validated against the schema by a generator subcommand, since schema validity is the only automatic check possible.
- **Privacy.** Personal data (name, DNI, address, card digits) is covered in the photo before it is stored. Company data printed by the issuer stays, because it is part of what is extracted.
- **Pending.** Where a printed "IVA Contenido" goes is decided when the photos arrive (Open Questions).

### D11 · Dependencies

Add `pdfplumber` (which brings `pypdfium2`) to `tools/generate_invoices/requirements.txt`, pinned to the versions verified in exploration. Pillow is already pinned. Nothing is added to the extractor's `pyproject.toml`.

## Risks / Trade-offs

- [The visibility map is wrong for a letter I have not rendered yet (C, E, B consumidor final)] → Task 2 renders one case per letter and category and checks it by eye before the map is used. Verification then catches any non-null value that is not printed.
- ["0,00" and other common strings pass verification in the wrong cell] → Human review of every document. Accepted as a known blind spot (D2).
- [A `null` field that is actually printed goes unnoticed] → Human review, with a checklist that lists the `null` fields of each document next to the PDF.
- [pyfepdf breaks on long descriptions or many items (multi-page)] → `LanzarExcepciones = True` fails loudly; the case is adjusted and the change recorded in `cases.py`.
- [Editing CSV coordinates for `qr_variant` takes longer than expected] → Limited to labels and two swapped columns. If it exceeds ~1 h, fall back to labels only and record it.
- [libjpeg or pypdfium2 differences across machines break pixel identity] → Versions recorded. The contract states pixel identity only under the recorded versions, and ground truth identity does not depend on them.
- [15/15 layout split with ~12 in-domain invoices per layout detects only large differences] → Accepted. Stated in PRD 02 and in the stage 3 report.
- [Synthetic CUITs with valid check digits collide with real legal entities] → Unavoidable with valid digits. Legal-entity prefixes only (30/33/34), and noted in README limitations (stage 5).

## Migration Plan

Not applicable: no deployed system. The spike stays as a reference until the generator reproduces its Factura A. A task then removes it or reduces it to a pointer.

## Open Questions

- **"IVA Contenido" on real tickets.** When a real ticket prints it, which ground-truth field holds it, and does it stay `null`? This affects only the hand annotation of `ground_truth_real/`. It does not change the synthetic dataset, these specs or the task breakdown. It is decided when the photos arrive.
