## Purpose

Defines the evaluation dataset for the extractor and the generator that produces it: which documents it contains, how their ground truth is built and verified against what is actually printed, what the manifest records, and how a separate set of real documents is kept apart from the metrics.

## ADDED Requirements

### Requirement: Generator is isolated from the extractor

The dataset generator SHALL live outside the extractor package, with its own dependency set, and SHALL NOT be imported by extractor code. Generator code that uses GPL-3.0 components SHALL be marked as GPL-3.0.

#### Scenario: No import from the extractor
- **WHEN** the extractor package source is searched for imports of the generator or of pyafipws
- **THEN** no such import exists

### Requirement: Reproducible generation

Every synthetic document SHALL be generated from a seed and a parameter set. Given the same seed and the same pinned generator dependencies, regeneration SHALL produce:
- ground truth that is byte-identical;
- a clean PDF that is byte-identical, including its creation date;
- degraded documents that are pixel-identical.

The generator version (git commit and pinned rendering dependency versions) SHALL be recorded for every document.

#### Scenario: Regenerate a clean document
- **WHEN** a clean invoice is regenerated from its manifest seed with the recorded dependency versions
- **THEN** its PDF bytes and its ground truth bytes are identical to the committed files

#### Scenario: Regenerate a degraded document
- **WHEN** a degraded document is regenerated from its manifest seed with the recorded dependency versions
- **THEN** its decoded pixels and its ground truth are identical to the committed files

#### Scenario: Uncommitted generator code
- **WHEN** generation is started while the generator directory has modified or untracked files
- **THEN** generation is refused, the uncommitted files are listed, and no document or manifest is written

### Requirement: Generation fails loudly

A rendering error SHALL abort generation of that document. The generator SHALL NOT write a document file or its ground truth when rendering or verification failed.

#### Scenario: Rendering error
- **WHEN** the rendering engine raises an error for a document
- **THEN** no PDF, image or ground truth file is written for it and the error is reported

### Requirement: Valid synthetic identifiers and consistent arithmetic

Synthetic CUITs SHALL carry a correct mod-11 check digit and SHALL use legal-entity prefixes (30, 33 or 34), never the prefixes assigned to natural persons. CAE numbers SHALL have 14 digits. Amounts SHALL be exact decimals with explicit rounding, and each invoice SHALL be arithmetically consistent: items sum to net, VAT per rate matches its base, and the printed total equals net plus non-taxed plus exempt plus VAT plus other taxes.

#### Scenario: CUIT check digit
- **WHEN** any CUIT in a synthetic ground truth is checked with the mod-11 algorithm
- **THEN** the check digit is valid and the prefix is 30, 33 or 34

#### Scenario: Totals close
- **WHEN** the components of any synthetic invoice are summed from its generator parameters
- **THEN** they equal its total exactly

### Requirement: Dataset composition

The synthetic dataset SHALL contain exactly 30 documents:
- **25 in-domain invoices:** A ×10, B ×7, C ×5, E ×3.
- **5 negatives:** 1 remito and 1 presupuesto (expected reason `not_an_invoice`); 1 nota de crédito A, 1 nota de débito B and 1 recibo (expected reason `unsupported_document_type`).

Documents SHALL be split 15/15 between the two layouts. Difficulty tags SHALL cover every one of: `multi_page`, `foreign_currency`, `skewed_scan`, `image_input`, `missing_optional`, `not_an_invoice`, `unsupported_document`, `dense_table`. At least 8 documents SHALL carry a tag. Exactly 4 documents SHALL be degraded: 2 as PDFs with no text layer (`skewed_scan`) and 2 as JPG images (`image_input`). Each degraded document SHALL be a distinct invoice, not a copy of another document in the set.

#### Scenario: Composition check
- **WHEN** the manifest is aggregated
- **THEN** it lists 30 documents with the stated counts per document kind, invoice letter and layout, and every required tag appears at least once

#### Scenario: Foreign currency is visible
- **WHEN** a Factura E in USD or EUR is rendered
- **THEN** the document prints its currency and its exchange rate

### Requirement: Ground truth is what the document prints

Ground truth for an in-domain invoice SHALL be the extraction result of the `invoice-schema` capability with outcome `extracted`, holding the values as printed on the rendered document rather than the generator's input. Optional values that the document does not print SHALL be explicit `null`, never omitted and never computed. Lists SHALL keep document order. The only value not taken from the print is `currency`, which is `ARS` when no currency is printed, by the schema convention. Synthetic B invoices SHALL NOT print an "IVA Contenido" line. When they print a per-item VAT rate, that rate SHALL be in the ground truth. Ground truth for a negative SHALL be a failed result with its expected reason.

#### Scenario: Net not printed on a Factura B
- **WHEN** ground truth is written for a synthetic Factura B
- **THEN** `net_amount` is `null` even though the generator knows the net

#### Scenario: Truncated description
- **WHEN** the template shortens or wraps an item description
- **THEN** the ground truth holds the description as printed

#### Scenario: Negative ground truth
- **WHEN** ground truth is written for the nota de crédito A
- **THEN** it is a failed result with reason `unsupported_document_type`

#### Scenario: Schema validity
- **WHEN** every ground truth file is validated against the extraction result schema
- **THEN** all of them validate

### Requirement: Field-by-field verification against the clean document

Before ground truth is written, every non-null leaf value of an in-domain invoice SHALL be formatted as it is printed (for example amounts as "338.650,00", dates as "12/08/2026", CUITs as "30-71234567-1") and SHALL be found in the text layer of the clean rendered PDF. Values that are not printed by convention (`currency` without a printed label) SHALL be listed as skipped. A document with any value not found SHALL fail generation. The number of checked fields, the skipped fields and the result SHALL be recorded in the manifest.

#### Scenario: Value not printed
- **WHEN** a ground truth value is not found in the clean PDF text in its printed format
- **THEN** generation of that document fails and names the field

#### Scenario: Check recorded
- **WHEN** a document passes verification
- **THEN** its manifest entry records how many fields were checked, which were skipped, and that it passed

### Requirement: Degraded documents inherit verified ground truth

A degraded document SHALL be produced from a clean rendered PDF that passed verification. Its ground truth SHALL be that clean document's ground truth. Degraded documents delivered as PDF SHALL contain no text layer. The manifest SHALL record the hash of the clean source and the degradation parameters (resolution, rotation, noise, JPEG quality where applicable).

#### Scenario: No text layer
- **WHEN** text is extracted from a `skewed_scan` PDF
- **THEN** no text is returned

#### Scenario: Provenance
- **WHEN** a degraded document's manifest entry is read
- **THEN** it names the clean source hash and every degradation parameter used

### Requirement: Manifest

`ground_truth/manifest.jsonl` SHALL have one entry per document with: `id`, `file`, `format`, `source` (`synthetic` or `real`), `seed`, `generator_version`, `layout`, `document_kind`, `printed_letter`, `tags`, `pages`, `degradation`, `expected_outcome` (`extracted` or `explicit_failure`), `expected_reason`, `gt_check`, `reviewed_by` and `reviewed_at`. Fields that do not apply SHALL be `null`. `printed_letter` SHALL record the letter printed on the document and SHALL NOT imply the invoice type: a nota de crédito A has printed letter `A` and expected outcome `explicit_failure`.

#### Scenario: Negative entry
- **WHEN** the manifest entry of the remito is read
- **THEN** it has `document_kind` `remito`, `printed_letter` `R`, `expected_outcome` `explicit_failure` and `expected_reason` `not_an_invoice`

### Requirement: Expected failure reason is informative, not scored

`expected_reason` SHALL be recorded for every negative. Reports SHALL be able to state reason agreement, but a negative whose actual failure reason differs from the expected one SHALL still count as a correct rejection under the measurement rules.

#### Scenario: Different reason
- **WHEN** the nota de crédito A is rejected with reason `not_an_invoice`
- **THEN** it counts as a correct rejection and as a reason mismatch

### Requirement: Human review of every document

Every document SHALL be opened and compared by eye against its ground truth before the dataset is considered complete, and its manifest entry SHALL record who reviewed it and when.

#### Scenario: Unreviewed document
- **WHEN** any manifest entry has `reviewed_by` or `reviewed_at` set to `null`
- **THEN** the dataset is not complete

### Requirement: Few-shot examples never come from the evaluation set

Documents used as examples in prompts SHALL be generated with seeds disjoint from the seeds in the manifest and SHALL NOT be taken from `ground_truth/`.

#### Scenario: Seed overlap
- **WHEN** the seeds of any prompt example are compared with the manifest seeds
- **THEN** they do not overlap

### Requirement: Separate real set

Real documents SHALL live in `ground_truth_real/`, which SHALL be git-ignored. They SHALL be annotated by hand, use the manifest format with `source` `real` and no seed, generator version, degradation or field check, and SHALL be reported separately from the synthetic dataset. They SHALL NOT be included in any headline metric.

#### Scenario: Not committed
- **WHEN** git is asked whether a file under `ground_truth_real/` is ignored
- **THEN** it is ignored

#### Scenario: Not in headline metrics
- **WHEN** the synthetic dataset is aggregated for a report
- **THEN** no document with `source` `real` is counted
