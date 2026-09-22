## Purpose

Turns one document into one final outcome: extract, validate, and, when the extraction is inconsistent or fails client-side schema validation, ask the model for a correction with the problems in context, under a hard attempt cap that ends in an explicit failure rather than an invalid object.

## ADDED Requirements

### Requirement: Final outcome per document

Processing a document SHALL end in exactly one final outcome: an accepted invoice with no validation problems, a model-reported failure (the schema's failure outcome with its reason), a validation failure carrying the remaining problems, or a call failure (truncated, refused, invalid output after the cap, API error). A document SHALL NOT end with an invoice that has validation problems presented as accepted.

#### Scenario: Valid on the first attempt
- **WHEN** the first extraction passes validation
- **THEN** the outcome is the accepted invoice after one attempt

#### Scenario: Model reports a failure
- **WHEN** the model returns the failure outcome `not_an_invoice`
- **THEN** the outcome is that model-reported failure, no validation runs and no corrective attempt is made

### Requirement: Corrective attempt carries the previous extraction and its problems

When an extraction fails validation, or fails client-side schema validation, the next attempt SHALL resend the document with the previous model output and the list of problems in the conversation, and SHALL ask for a corrected extraction or an explicit failure when the document does not allow a consistent extraction. The corrective instructions SHALL come from a versioned prompt file.

#### Scenario: Problems in the next request
- **WHEN** the first extraction fails `V3` on `total`
- **THEN** the second request contains the document, the first output as the previous assistant turn, and a user turn that lists the `V3` problem

#### Scenario: Client-side schema failure is corrected
- **WHEN** the first response fails output-model validation with an `invalid_output` failure
- **THEN** the second request carries the validation errors as the problems to correct

#### Scenario: Success on attempt 2
- **WHEN** the first extraction fails validation and the second passes
- **THEN** the outcome is the second invoice, accepted, after 2 attempts

### Requirement: Hard attempt cap

The number of attempts per document SHALL be capped, with a default of 3, configurable, and never unbounded. When the last attempt still fails validation, the outcome SHALL be a validation failure carrying the remaining problems and the last extraction marked as rejected.

#### Scenario: Cap reached
- **WHEN** a fake client always returns an invoice that fails `V3`, and the cap is 3
- **THEN** exactly 3 requests are sent and the outcome is a validation failure listing the `V3` problem

#### Scenario: Cap cannot be disabled
- **WHEN** the attempt cap is configured as 0, a negative number or unbounded
- **THEN** configuration is rejected before any request is sent

### Requirement: Non-correctable call failures end the document

A truncated, refused or API-error call SHALL end the document with that call failure and SHALL NOT trigger a corrective attempt.

#### Scenario: Truncated output
- **WHEN** the first call ends with stop reason `max_tokens`
- **THEN** the outcome is a `truncated` call failure after 1 attempt

### Requirement: Attempts, cost and latency cover every attempt

The document's record SHALL keep every attempt (its call record and its validation problems), the corrective attempt count, the transport request count of each call, and cost and latency summed over every attempt. Transport retries SHALL NOT count as corrective attempts.

#### Scenario: Cost over attempts
- **WHEN** a document succeeds on attempt 2 with calls costing $0.04 and $0.05
- **THEN** its recorded cost is $0.09 and its attempt count is 2

#### Scenario: Transport retry is not an attempt
- **WHEN** the first call needed two transport requests after a 529 and then passed validation
- **THEN** the document has 1 corrective attempt and 2 transport requests

### Requirement: Validation can be switched off for a measured run

Processing SHALL support running with validation off, in which case the first extraction is the outcome and no corrective attempt is made, so the effect of validation and retries can be measured as one lever.

#### Scenario: Validation off
- **WHEN** processing runs with validation off and the extraction would fail `V3`
- **THEN** the outcome is that extraction after 1 attempt
