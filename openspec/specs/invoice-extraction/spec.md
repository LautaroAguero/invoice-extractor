# invoice-extraction Specification

## Purpose

Extracts one invoice document into the extraction result using a versioned prompt and the model client, and reports what the call cost and how it ended.

## Requirements

### Requirement: Versioned prompt files

Extraction instructions SHALL be loaded from `prompts/extract_invoice/vN.md` by version and SHALL NOT be written inline in code. Requesting a version that does not exist SHALL be an error, never a fallback to another version.

#### Scenario: Load v1
- **WHEN** extraction is configured with prompt version `v1`
- **THEN** the system prompt is the content of `prompts/extract_invoice/v1.md`

#### Scenario: Missing version
- **WHEN** extraction is configured with prompt version `v9` and that file does not exist
- **THEN** extraction fails with an error before any model call

### Requirement: v1 prompt is minimal

The v1 prompt SHALL contain only a role, the task, and the instruction to use the failure outcome when the document is not a supported invoice or a mandatory value is not visible, never guessing. It SHALL NOT contain examples or field-specific tuning.

#### Scenario: v1 content review
- **WHEN** `prompts/extract_invoice/v1.md` is reviewed
- **THEN** it has no examples and it instructs the model to return a failure rather than guess

### Requirement: Instructions in the system prompt, document in the user turn

The extraction request SHALL place the prompt in the system prompt and SHALL place only the document content block in the user turn.

#### Scenario: Message layout
- **WHEN** a PDF is extracted
- **THEN** the request's system prompt is the prompt file content and the single user message contains only the PDF document block

### Requirement: Single-document extraction

Given a path to a PDF or JPG file, extraction SHALL return the model client's call record with the extraction result as its parsed outcome (or a call failure), plus the prompt version used. A PDF SHALL be sent as a document content block. A JPG SHALL be sent as an image content block. A file that is neither a PDF nor a JPG SHALL be rejected before any model call.

#### Scenario: PDF input
- **WHEN** extraction runs on a PDF file
- **THEN** it returns a record with the outcome, metrics and prompt version, and the request's user turn contains a document block

#### Scenario: JPG input
- **WHEN** extraction runs on a `.jpg` file
- **THEN** it returns a record with the outcome, metrics and prompt version, and the request's user turn contains an image block

#### Scenario: Non-PDF input
- **WHEN** extraction runs on a file that is neither a PDF nor a JPG (for example a `.txt` file)
- **THEN** it fails with an unsupported input error and no model call is made

### Requirement: Printed call summary

The single-document entry point SHALL print the model ID, input and output tokens, cache tokens, stop reason, latency, cost in USD and the outcome (extracted, model failure with reason, or call failure with kind).

#### Scenario: Summary after a truncated call
- **WHEN** the entry point runs with a maximum output token count too small for the response
- **THEN** it prints a `truncated` call failure together with tokens, stop reason, latency and cost, and exits without a traceback

### Requirement: Acceptance on synthetic documents

Running the entry point against real model calls SHALL be validated manually on three documents: the spike Factura A, a nota de crédito rendered from the same spike, and a one-page non-invoice PDF. These runs SHALL NOT be part of the automated test suite.

#### Scenario: Spike Factura A
- **WHEN** the entry point runs on the spike Factura A
- **THEN** the outcome is extracted and total, issuer CUIT, customer CUIT, point of sale, invoice number and CAE number match the rendered values

#### Scenario: Nota de crédito
- **WHEN** the entry point runs on the nota de crédito rendered from the spike
- **THEN** the outcome is a failure with reason `unsupported_document_type`

#### Scenario: Non-invoice document
- **WHEN** the entry point runs on a one-page non-invoice PDF
- **THEN** the outcome is a failure with a reason, not an extracted invoice
