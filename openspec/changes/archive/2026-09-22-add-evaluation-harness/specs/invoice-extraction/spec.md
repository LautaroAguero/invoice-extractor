## MODIFIED Requirements

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
