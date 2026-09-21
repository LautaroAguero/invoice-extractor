## Purpose

Compares the document-block ingestion path against a local-text ingestion path on the same documents, to decide with evidence which one the extractor should use for this domain.

## ADDED Requirements

### Requirement: Two ingestion paths

Path A SHALL send the PDF as a document content block and a JPG as an image content block. Path B SHALL extract text locally with `pdfplumber`'s default-mode `extract_text()` over all pages and send it as text content, performing no OCR.

#### Scenario: Path B has no OCR
- **WHEN** path B runs on a document with no extractable text layer
- **THEN** no image is sent to the model and no text is invented from the image

### Requirement: Paired comparison

Both paths SHALL run over the same set of documents. The comparison SHALL be paired: McNemar's exact test on per-document outcome, and per-field precision deltas computed only over documents both paths extracted.

#### Scenario: Paired outcome test
- **WHEN** the comparison is computed
- **THEN** it reports a McNemar exact test result over the documents both paths attempted

### Requirement: No-text-layer and image-only documents fail explicitly on path B

For a document with no text layer or a document available only as an image, path B SHALL end in an explicit failure and SHALL NOT produce an extraction from empty text. These documents SHALL be reported in a separate group from the paired precision comparison, because they measure coverage rather than extraction quality.

#### Scenario: Skewed scan on path B
- **WHEN** path B runs on a document tagged `skewed_scan` (image-only PDF)
- **THEN** the outcome is an explicit failure, not an extraction

#### Scenario: JPG-only document on path B
- **WHEN** path B runs on a document tagged `image_input`
- **THEN** the outcome is an explicit failure, not an extraction

#### Scenario: PDF that cannot be parsed on path B
- **WHEN** path B runs on a PDF whose structure cannot be parsed
- **THEN** the outcome for that document is an explicit failure with no model call, and the run continues with the remaining documents

### Requirement: Comparison result table

The comparison result SHALL report, per path: field precision, invented value count, cost per document and p95 latency, and SHALL name the winning path for this domain together with its trade-off.

#### Scenario: Winner is named
- **WHEN** the comparison is rendered
- **THEN** it states which path wins and what it trades off against the other
