## Purpose

Defines the extraction result contract for Argentine invoices: the outcome that is either an extracted invoice or a typed failure, the fields an invoice carries, which of them are mandatory, and how values are encoded.

## ADDED Requirements

### Requirement: Result is either an extracted invoice or a typed failure

The extraction result SHALL have exactly one of two outcomes, distinguished by an `outcome` discriminator: `extracted`, carrying an invoice, or `failed`, carrying a failure reason and a free-text detail. A result SHALL NOT carry both an invoice and a failure, and SHALL NOT carry neither.

#### Scenario: Extracted result
- **WHEN** a result with outcome `extracted` and a valid invoice is validated
- **THEN** validation succeeds and the invoice is accessible

#### Scenario: Failed result
- **WHEN** a result with outcome `failed`, a reason and a detail is validated
- **THEN** validation succeeds and no invoice is present

#### Scenario: Mixed result is rejected
- **WHEN** a result with outcome `failed` that also carries invoice data is validated
- **THEN** validation fails

### Requirement: Failure reasons are a closed set

The failure reason SHALL be one of `not_an_invoice`, `unsupported_document_type`, `illegible` or `missing_mandatory_data`. Notas de crédito, notas de débito and factura M SHALL be represented as `unsupported_document_type`. `missing_mandatory_data` SHALL be used only when the document is a supported invoice and a mandatory field is not visible, and its detail SHALL name the missing field.

#### Scenario: Unknown reason is rejected
- **WHEN** a failed result with reason `low_confidence` is validated
- **THEN** validation fails

#### Scenario: Nota de crédito
- **WHEN** ground truth is written for a nota de crédito A
- **THEN** it is a failed result with reason `unsupported_document_type`

### Requirement: Mandatory invoice fields

An extracted invoice SHALL require: `invoice_type`, `point_of_sale`, `invoice_number`, `issue_date`, `issuer.name`, `issuer.cuit`, `issuer.vat_condition`, `customer.vat_condition`, `currency`, `total`, `cae.number`, `cae.expiry_date`, and `items` with at least one item. Every other field SHALL be optional.

#### Scenario: Missing mandatory field
- **WHEN** an invoice without `cae.number` is validated
- **THEN** validation fails

#### Scenario: Empty items list
- **WHEN** an invoice with an empty `items` list is validated
- **THEN** validation fails

#### Scenario: Consumer invoice without customer identity
- **WHEN** an invoice has `customer.vat_condition` set and `customer.name`, `customer.cuit` and `customer.address` set to `null`
- **THEN** validation succeeds

### Requirement: Values not printed on the document are null

The following fields SHALL be optional and SHALL accept an explicit `null`: `due_date`, `exchange_rate`, `document_code`, `customer.name`, `customer.cuit`, `customer.address`, `net_amount`, `vat_amount`, `non_taxed_amount`, `exempt_amount`, `items[].code`, `items[].discount` and `items[].vat_rate`. Their descriptions SHALL state that they are `null` when the value is not printed on the document. The lists `vat_breakdown` and `other_taxes` SHALL be required and SHALL be empty when nothing is printed.

#### Scenario: Factura B without discriminated VAT
- **WHEN** an invoice of type B has `net_amount`, `vat_amount` and every `items[].vat_rate` set to `null` and an empty `vat_breakdown`
- **THEN** validation succeeds

#### Scenario: Omitted list
- **WHEN** an invoice without the `other_taxes` key is validated
- **THEN** validation fails

### Requirement: Currency defaults by fiscal convention

`currency` SHALL be required. Its description SHALL state that the value is `ARS` when the document shows no currency.

#### Scenario: Peso invoice with no currency label
- **WHEN** ground truth is written for an invoice that prints no currency
- **THEN** `currency` is `ARS`

### Requirement: Total components

An invoice SHALL carry every component of the ARCA total: `net_amount`, `non_taxed_amount`, `exempt_amount`, `vat_amount`, `vat_breakdown` (items of `rate`, `amount`), `other_taxes` (items of `description`, `amount`) and `total`. The schema SHALL NOT enforce arithmetic between them.

#### Scenario: Invoice with a perception
- **WHEN** an invoice prints one "Percepción IIBB" line
- **THEN** it is represented as one `other_taxes` item with its description and amount

#### Scenario: Inconsistent totals still validate
- **WHEN** an invoice whose components do not add up to `total` is validated
- **THEN** schema validation succeeds (consistency is a business check, not a schema rule)

### Requirement: Item fields

Each item SHALL carry `description`, `quantity`, `unit_price` and `line_amount` (required) and `code`, `discount` and `vat_rate` (optional). Items SHALL NOT carry unit of measure or per-line VAT amount.

#### Scenario: Item from the spike invoice
- **WHEN** the row "HW-220 · Router dual band AX3000 · 2,00 · 0,00 · 48.500,00 · 21% · 97.000,00" is represented
- **THEN** the item has code `HW-220`, quantity `2`, discount `0`, unit price `48500.00`, VAT rate `21` and line amount `97000.00`

### Requirement: Closed enums

`invoice_type` SHALL be one of `A`, `B`, `C`, `E`. `currency` SHALL be one of `ARS`, `USD`, `EUR`. `vat_condition` (issuer and customer) SHALL be one of the ARCA receptor VAT conditions, with no catch-all member.

#### Scenario: Unsupported letter
- **WHEN** an invoice with `invoice_type` `M` is validated
- **THEN** validation fails

#### Scenario: Catch-all VAT condition
- **WHEN** an issuer with `vat_condition` `other` is validated
- **THEN** validation fails

### Requirement: Exact decimals and ISO dates

Amounts, quantities, rates and the exchange rate SHALL be parsed as exact decimals and SHALL be transmitted as strings of digits with an optional dot decimal separator, without thousands separators. Floats SHALL NOT appear in the parsed object. Dates SHALL be ISO `YYYY-MM-DD`.

#### Scenario: Exact amount
- **WHEN** a total of `"338650.00"` is parsed
- **THEN** the parsed value equals the exact decimal 338650.00 and is not a float

#### Scenario: Argentine number format is rejected
- **WHEN** a total of `"338.650,00"` is validated
- **THEN** validation fails

#### Scenario: ISO date
- **WHEN** an issue date of `"2026-08-12"` is parsed
- **THEN** the parsed value is the date 12 August 2026

### Requirement: Identifiers are digit strings without domain constraints

`issuer.cuit`, `customer.cuit`, `point_of_sale`, `invoice_number`, `cae.number` and `document_code` SHALL be strings whose descriptions ask for digits only, without separators, keeping leading zeros. The schema SHALL NOT enforce their length or check digit; those are business checks.

#### Scenario: Leading zeros preserved
- **WHEN** a point of sale `"00003"` is parsed
- **THEN** the parsed value is the string `00003`

#### Scenario: Wrong-length CAE still validates
- **WHEN** an invoice with a 13-digit `cae.number` is validated
- **THEN** schema validation succeeds

### Requirement: Every field is described with its printed label

Every field in the result schema SHALL have a non-empty description. When the document prints a label for the field, the description SHALL quote the literal Spanish label (for example "CUIT", "Fecha de Vto. CAE", "Bonif.").

#### Scenario: Description coverage
- **WHEN** the generated JSON Schema is inspected
- **THEN** every property at every level has a non-empty description

### Requirement: No model-reported confidence

The result schema SHALL NOT contain any confidence, certainty or score field.

#### Scenario: Confidence field absent
- **WHEN** the generated JSON Schema property names are inspected
- **THEN** none of them is a confidence, certainty or score field

### Requirement: Structural bounds

Within an invoice, object nesting SHALL NOT exceed two levels (for example `invoice > issuer`, or `invoice > items[]`). The schema SHALL meet the course minimum: at least 8 fields, 2 nested objects, 1 list, 1 enum and 2 optional fields.

#### Scenario: Nesting depth
- **WHEN** the invoice JSON Schema is traversed
- **THEN** no object property is nested deeper than two object levels below the invoice

#### Scenario: Course minimum
- **WHEN** the schema is inspected
- **THEN** it has at least 8 fields, 2 nested objects, 1 list, 1 enum and 2 optional fields
