## Purpose

Checks that a schema-valid extracted invoice is internally consistent, using the redundancies an Argentine invoice prints (check digits, arithmetic, fiscal rules per letter, dates, identifier formats), so an extraction that is well-shaped but wrong is detected before it is accepted.

## ADDED Requirements

### Requirement: Problems are returned, never raised

The validator SHALL take a parsed invoice and return a list of typed problems. Each problem SHALL name its check ID (`V1`, `V2`, `V2b`, `V3`, `V4`, `V5`, `V6`, `V7`), the field path it concerns, and a message that states the expected and the found value when both exist. An invoice with no problems SHALL return an empty list. The validator SHALL NOT raise for a business problem.

#### Scenario: Consistent invoice
- **WHEN** the validator receives an invoice whose every check passes
- **THEN** it returns an empty list

#### Scenario: Several problems at once
- **WHEN** an invoice has an invalid issuer CUIT check digit and a total that does not match its components
- **THEN** the validator returns one `V1` problem for `issuer.cuit` and one `V3` problem for `total`, and raises nothing

### Requirement: Deterministic and independent of the model

The validator SHALL be deterministic: the same invoice and the same reference date SHALL always produce the same problems. It SHALL NOT depend on the model client, the prompts or any network access. The reference date for date checks SHALL be an input, not read from the clock inside a check.

#### Scenario: Same input, same problems
- **WHEN** the validator runs twice on the same invoice with the same reference date
- **THEN** both runs return identical problem lists

#### Scenario: Validation without credentials
- **WHEN** the validator's tests run with no API key and no network
- **THEN** they pass

### Requirement: Rounding tolerance

An arithmetic check SHALL accept a difference up to 0.01 times the number of independently rounded amounts it sums: 0.01 × the number of items for a sum over items, 0.01 × the number of summed terms for a total, and 0.01 for a single line product. A difference beyond the tolerance SHALL be a problem.

#### Scenario: Per-line rounding within tolerance
- **WHEN** four items sum to 0.03 more than the printed net amount
- **THEN** `V2` reports no problem

#### Scenario: Difference beyond tolerance
- **WHEN** four items sum to 0.05 more than the printed net amount
- **THEN** `V2` reports a problem

### Requirement: V1 CUIT check digit

The issuer CUIT, and the customer CUIT when present, SHALL have 11 digits and a valid mod-11 check digit (weights 5,4,3,2,7,6,5,4,3,2). A base whose check digit would be 10 SHALL be invalid.

#### Scenario: Wrong check digit
- **WHEN** the issuer CUIT is `30712345671` and the valid check digit for base `3071234567` is 3
- **THEN** `V1` reports a problem on `issuer.cuit`

#### Scenario: Absent customer CUIT
- **WHEN** the customer CUIT is null
- **THEN** `V1` does not check it

### Requirement: V2 items sum to the net amount

When the net amount is printed, the sum of item line amounts SHALL equal it within tolerance. When the net amount is not printed, `V2` SHALL not run.

#### Scenario: Items do not reach the net
- **WHEN** a Factura A prints a net of 540200.00 and its items sum to 440200.00
- **THEN** `V2` reports a problem on `net_amount`

### Requirement: V2b line arithmetic

For each item, quantity × unit price − discount (absent discount counts as zero) SHALL equal the line amount within 0.01.

#### Scenario: Misread quantity
- **WHEN** an item has quantity 3, unit price 138800.00, no discount and line amount 277600.00
- **THEN** `V2b` reports a problem on that item's line amount

### Requirement: V3 total

When the net amount is printed, net + non-taxed + exempt + VAT + sum of other taxes SHALL equal the total within tolerance, where absent terms count as zero and VAT is the printed `vat_amount` or, when that is not printed, the sum of `vat_breakdown`. When the net amount is not printed, the sum of item line amounts plus the sum of other taxes SHALL equal the total within tolerance.

#### Scenario: Factura A total
- **WHEN** a Factura A prints net 540200.00, VAT lines 21% 94500.00 and 10.5% 17325.00, and total 652025.00
- **THEN** `V3` reports no problem

#### Scenario: Invoice without a printed net
- **WHEN** a Factura C prints no net and its items sum to exactly its total
- **THEN** `V3` reports no problem

### Requirement: V4 VAT per rate

For each VAT breakdown line, its amount SHALL equal base × rate / 100 within 0.01 × the number of items at that rate, where the base is the sum of the line amounts of the items with that `vat_rate`. A breakdown rate with no item at that rate SHALL be a problem.

#### Scenario: VAT line amount off
- **WHEN** items at 21% sum to 450000.00 and the 21% breakdown line prints 84500.00
- **THEN** `V4` reports a problem on that breakdown line

### Requirement: V5 invoice type rules

- A Factura A SHALL have a customer CUIT, a VAT breakdown or a VAT amount, and a VAT rate on every item.
- A Factura B or C SHALL have an empty VAT breakdown and no VAT amount.
- A Factura C or E SHALL have no item VAT rate.
- A foreign-currency invoice SHALL have an exchange rate, and an ARS invoice SHALL have none.
- When a document code is printed, it SHALL match the letter (A 01, B 06, C 11, E 19).

A Factura B item MAY carry a VAT rate, because a Factura B to a consumidor final prints an IVA column.

#### Scenario: Factura A without customer CUIT
- **WHEN** a Factura A has a null customer CUIT
- **THEN** `V5` reports a problem on `customer.cuit`

#### Scenario: Factura B with item VAT rates
- **WHEN** a Factura B has no VAT breakdown and every item carries a VAT rate
- **THEN** `V5` reports no problem

#### Scenario: Letter and code disagree
- **WHEN** the letter is B and the printed document code is 01
- **THEN** `V5` reports a problem on `document_code`

### Requirement: V6 date coherence

The issue date SHALL NOT be after the reference date; the due date, when present, SHALL NOT be before the issue date; the CAE expiry date SHALL NOT be before the issue date.

#### Scenario: CAE expired before issue
- **WHEN** the CAE expiry date is one day before the issue date
- **THEN** `V6` reports a problem on `cae.expiry_date`

### Requirement: V7 identifier formats

The point of sale SHALL have 5 digits, the invoice number 8 digits and the CAE number 14 digits.

#### Scenario: Short CAE
- **WHEN** the CAE number has 13 digits
- **THEN** `V7` reports a problem on `cae.number`

### Requirement: No false rejections on ground truth

Every in-domain ground-truth invoice of the synthetic dataset SHALL pass validation with no problems, using its issue date as the reference date or later.

#### Scenario: Ground truth passes
- **WHEN** the validator runs on every in-domain invoice in `ground_truth/`
- **THEN** it returns no problem for any of them
