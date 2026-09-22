## MODIFIED Requirements

### Requirement: Content blocks in, structured output out

The client SHALL accept a system prompt, a conversation and an output model, and SHALL request the output through native structured outputs with that model. The conversation SHALL be either a list of content blocks for a single user turn, or an alternating sequence of user and assistant turns that starts and ends with a user turn. It SHALL support PDF document blocks. It SHALL NOT extract structured data by parsing free text. It SHALL NOT depend on any invoice-specific type.

#### Scenario: PDF document block
- **WHEN** the client is called with one PDF document block
- **THEN** the request contains that block in the user turn and requests structured output for the given output model

#### Scenario: Generic output model
- **WHEN** the client is called with an output model unrelated to invoices
- **THEN** it returns a record whose parsed outcome is an instance of that model

#### Scenario: Multi-turn conversation
- **WHEN** the client is called with a user turn, an assistant turn holding a previous output, and a second user turn
- **THEN** the request carries the three turns in that order and requests structured output for the given output model

#### Scenario: Malformed conversation
- **WHEN** the conversation ends with an assistant turn or has two consecutive turns of the same role
- **THEN** the call raises a usage error and no request is sent

### Requirement: Per-call record

Every call SHALL return a record with: the outcome, model ID, stop reason, input tokens, output tokens, cache read input tokens, cache creation input tokens, latency in milliseconds, cost in USD, request ID, and the number of transport requests the call sent (1 when no transport retry happened). The outcome SHALL be either the parsed output or a typed call failure.

#### Scenario: Successful call
- **WHEN** a call ends with stop reason `end_turn` and a valid output
- **THEN** the record has a parsed outcome and every metric field populated, with 1 transport request

#### Scenario: Transport retry counted
- **WHEN** the first transport request returns HTTP 529 and the retry succeeds
- **THEN** the record reports 2 transport requests

#### Scenario: Concurrent calls count independently
- **WHEN** two calls run concurrently on one client and only one of them is retried
- **THEN** each record reports only its own transport requests
