# model-client Specification

## Purpose

An instrumented, failure-aware call to the model that returns a structured output validated against a caller-provided model, together with a per-call record of tokens, stop reason, latency and cost.

## Requirements

### Requirement: Content blocks in, structured output out

The client SHALL accept a system prompt, a list of content blocks and an output model, and SHALL request the output through native structured outputs with that model. It SHALL support PDF document blocks. It SHALL NOT extract structured data by parsing free text. It SHALL NOT depend on any invoice-specific type.

#### Scenario: PDF document block
- **WHEN** the client is called with one PDF document block
- **THEN** the request contains that block in the user turn and requests structured output for the given output model

#### Scenario: Generic output model
- **WHEN** the client is called with an output model unrelated to invoices
- **THEN** it returns a record whose parsed outcome is an instance of that model

### Requirement: Per-call record

Every call SHALL return a record with: the outcome, model ID, stop reason, input tokens, output tokens, cache read input tokens, cache creation input tokens, latency in milliseconds, cost in USD and request ID. The outcome SHALL be either the parsed output or a typed call failure.

#### Scenario: Successful call
- **WHEN** a call ends with stop reason `end_turn` and a valid output
- **THEN** the record has a parsed outcome and every metric field populated

### Requirement: No hidden accumulation

The client SHALL NOT keep cumulative usage, cost or call counts across calls. Each record SHALL describe only its own call.

#### Scenario: Independent records
- **WHEN** the same client makes two calls with different token usage
- **THEN** each record's tokens and cost match its own call only

### Requirement: Cost computed from usage

Cost SHALL be computed from the response `usage` and the configured price table, including cache read and cache creation tokens at their configured multipliers. Thinking tokens SHALL be costed as output tokens as reported in `usage`.

#### Scenario: Cost arithmetic
- **WHEN** usage reports 5,000 input, 2,000 output and no cache tokens for a model priced at $2 input and $10 output per million tokens
- **THEN** the recorded cost is $0.03

#### Scenario: Cache tokens are costed
- **WHEN** usage reports cache read tokens
- **THEN** the recorded cost includes them at the input price times the configured cache read multiplier

### Requirement: Model and prices are configuration

Model ID, maximum output tokens, timeout, transport retry ceiling and the price table SHALL come from configuration, not code. Each price entry SHALL carry the date it was verified. A call for a model without a price entry SHALL fail before any request is sent.

#### Scenario: Unknown model
- **WHEN** the configured model has no entry in the price table
- **THEN** the call raises a configuration error and no request is sent

#### Scenario: Price verification date
- **WHEN** the price table is loaded
- **THEN** every entry exposes its verification date

### Requirement: Truncated and refused output are typed failures

When the stop reason is `max_tokens` the outcome SHALL be a `truncated` call failure. When the stop reason is `refusal` the outcome SHALL be a `refused` call failure. The stop reason SHALL be checked before any parsed output is read, and no partial object SHALL be returned. Tokens and cost SHALL still be recorded.

#### Scenario: Truncation
- **WHEN** a response ends with stop reason `max_tokens`
- **THEN** the outcome is a `truncated` failure, no exception propagates, and tokens and cost are recorded

#### Scenario: Refusal
- **WHEN** a response ends with stop reason `refusal`
- **THEN** the outcome is a `refused` failure and tokens and cost are recorded

### Requirement: Invalid output is a typed failure

When the response fails client-side validation against the output model, the outcome SHALL be an `invalid_output` call failure carrying the validation errors. Tokens and cost SHALL still be recorded.

#### Scenario: Output violating a client-side constraint
- **WHEN** the response is shape-valid for the API but fails output-model validation
- **THEN** the outcome is an `invalid_output` failure listing the errors

### Requirement: Transport failures are bounded and typed

Rate limits, overload, server errors, connection errors and timeouts SHALL be retried by the SDK with exponential backoff up to a configured ceiling that cannot be unlimited. When retries are exhausted, or on a non-retryable request error, the outcome SHALL be an `api_error` call failure. Authentication, permission and unknown-model errors SHALL be raised, because every later call would fail the same way. Transport retries SHALL NOT be counted as corrective attempts.

#### Scenario: Retries exhausted
- **WHEN** every attempt returns HTTP 529 until the retry ceiling
- **THEN** the outcome is an `api_error` failure and the latency covers all attempts

#### Scenario: Bad request
- **WHEN** the API returns HTTP 400
- **THEN** the outcome is an `api_error` failure without retries

#### Scenario: Authentication error
- **WHEN** the API returns HTTP 401
- **THEN** the call raises instead of returning a record

### Requirement: Async

The client SHALL expose its call as a coroutine, so callers can run several documents with bounded concurrency.

#### Scenario: Concurrent calls
- **WHEN** two calls are awaited concurrently on one client
- **THEN** both return independent records

### Requirement: Testable without the API

The client SHALL allow its SDK dependency to be replaced, so every behavior above can be tested with no API key and no network access.

#### Scenario: Test suite without credentials
- **WHEN** the test suite runs with no API key configured
- **THEN** all client tests pass without network access
