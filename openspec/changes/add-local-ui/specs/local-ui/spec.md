## Purpose

A local, single-user page for dropping invoices on: it classifies each document, shows every extracted value next to the source, and reports what the call actually cost, so the extractor can be used and judged without a terminal.

## ADDED Requirements

### Requirement: The UI is a thin layer

The UI SHALL obtain each document's outcome from the same entry point the command line uses, and SHALL NOT build prompts, call the model client, or apply business rules itself. Its own logic (building a result row, formatting values, session totals, the spend cap decision) SHALL be free of the UI framework, so it can be tested without it. The core package and its test suite SHALL NOT require the UI dependency.

#### Scenario: Tests without the UI dependency
- **WHEN** the test suite runs with no API key and without the UI extra installed
- **THEN** every test passes, including the UI's own logic tests

#### Scenario: No pipeline logic in the page
- **WHEN** the UI package is searched for prompt text, model requests or business rules
- **THEN** none are found; it calls one processing function

### Requirement: Upload and supported formats

The UI SHALL accept one or more PDF, JPG or PNG files per upload and process them one document at a time, showing progress. A file of any other format SHALL be rejected in the page with the same message the command line gives, before any model call.

#### Scenario: Unsupported file
- **WHEN** a `.txt` file is uploaded
- **THEN** the page shows it as rejected with the unsupported-input message and no model call is made

#### Scenario: Several files
- **WHEN** three documents are uploaded at once
- **THEN** each is processed and gets its own result row

### Requirement: Classification per document

Each processed document SHALL be presented as exactly one outcome: extracted, with its invoice type (A, B, C or E), or an explicit failure with its reason (`not_an_invoice`, `unsupported_document_type`, `illegible`, `missing_mandatory_data`), or a call failure with its kind (truncated, refused, invalid output, API error). A failure SHALL be visually distinct from a success and SHALL NOT be shown as a partially filled invoice.

#### Scenario: Invoice classified
- **WHEN** a Factura B is extracted
- **THEN** its row shows the outcome `extracted` and invoice type `B`

#### Scenario: Negative document
- **WHEN** a document that is not an invoice is processed and the model returns a failure
- **THEN** its row shows an explicit failure with the reason, marked as a failure, with no invoice fields

### Requirement: Measured numbers per document

Each row SHALL show, from that document's call record: cost in USD, input and output tokens, latency and attempts. The session SHALL show the running total cost and the number of documents processed. No number shown SHALL be an estimate.

#### Scenario: Cost comes from usage
- **WHEN** a document is processed
- **THEN** its row shows the cost computed from the call's reported usage, its token counts and its latency

#### Scenario: Session total
- **WHEN** two documents costing $0.04 and $0.03 have been processed
- **THEN** the session total shows $0.07 over 2 documents

### Requirement: Detail view

For an extracted document the UI SHALL show every schema field, including issuer, customer, dates, items, VAT breakdown, totals and CAE, and the raw JSON of the result. For a failure it SHALL show the reason and detail instead of invoice fields.

#### Scenario: Fields and raw JSON
- **WHEN** an extracted document's detail is opened
- **THEN** it shows the header fields, the items table, the VAT breakdown, the totals and the raw JSON

### Requirement: Bounded spend and missing credentials

The UI SHALL enforce a per-session spend cap with a safe default that cannot be disabled from the page. Once the cap is reached, no further document SHALL be processed, and the remaining documents SHALL be shown as not processed with that reason. When no API key is configured, the page SHALL say so with an actionable message and SHALL NOT attempt a call.

#### Scenario: Cap reached
- **WHEN** the session's spent total has reached the cap and another document is uploaded
- **THEN** it is shown as not processed because the spend cap was reached, and no model call is made

#### Scenario: Missing API key
- **WHEN** the page is opened with no API key configured
- **THEN** it shows how to configure one and does not attempt any call

### Requirement: Uploaded files stay local

Uploaded documents SHALL be written only to a temporary directory outside the repository and SHALL be deleted once the document is processed. No uploaded file or extraction result SHALL be written into the repository.

#### Scenario: Temporary file removed
- **WHEN** a document has been processed
- **THEN** its temporary file no longer exists and nothing was written inside the repository
