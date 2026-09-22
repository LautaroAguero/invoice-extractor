## MODIFIED Requirements

### Requirement: Single-document extraction

Given a path to a PDF, JPG or PNG file, extraction SHALL return the model client's call record with the extraction result as its parsed outcome (or a call failure), plus the prompt version used. A PDF SHALL be sent as a document content block. A JPG or PNG SHALL be sent as an image content block with its own media type. A file whose extension and magic bytes do not agree SHALL be rejected. A file that is none of those formats SHALL be rejected before any model call.

#### Scenario: PDF input
- **WHEN** extraction runs on a PDF file
- **THEN** it returns a record with the outcome, metrics and prompt version, and the request's user turn contains a document block

#### Scenario: JPG input
- **WHEN** extraction runs on a `.jpg` file
- **THEN** it returns a record with the outcome, metrics and prompt version, and the request's user turn contains an image block

#### Scenario: PNG input
- **WHEN** extraction runs on a `.png` file
- **THEN** the request's user turn contains an image block with media type `image/png`

#### Scenario: Extension and content disagree
- **WHEN** extraction runs on a file named `.png` whose bytes are not a PNG
- **THEN** it fails with an unsupported input error and no model call is made

#### Scenario: Non-PDF input
- **WHEN** extraction runs on a file that is none of PDF, JPG or PNG (for example a `.txt` file)
- **THEN** it fails with an unsupported input error and no model call is made
