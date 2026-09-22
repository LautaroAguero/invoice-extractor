## MODIFIED Requirements

### Requirement: Valid synthetic identifiers and consistent arithmetic

Synthetic CUITs SHALL carry a correct mod-11 check digit and SHALL use legal-entity prefixes (30, 33 or 34), never the prefixes assigned to natural persons. CAE numbers SHALL have 14 digits. Amounts SHALL be exact decimals with explicit rounding. Each invoice SHALL be arithmetically and fiscally consistent for its letter, and a reader SHALL be able to check the printed total from printed values alone:
- **Factura A:** items sum to net, VAT per rate matches its base, and the printed total equals net plus non-taxed plus exempt plus VAT plus other taxes.
- **Factura B:** printed unit prices and line amounts include VAT, and the printed line amounts sum to the printed total. The net and VAT that the renderer receives are exact and add up to that total.
- **Factura C:** no VAT. Items carry no VAT rate, the printed line amounts sum to the printed total, and the issuer's VAT condition is Responsable Monotributo.
- **Factura E:** no VAT, and the printed line amounts sum to the printed total.

A negative document that prints an invoice letter SHALL follow that letter's pricing rule.

#### Scenario: CUIT check digit
- **WHEN** any CUIT in a synthetic ground truth is checked with the mod-11 algorithm
- **THEN** the check digit is valid and the prefix is 30, 33 or 34

#### Scenario: Totals close
- **WHEN** the components of any synthetic invoice are summed from its generator parameters
- **THEN** they equal its total exactly

#### Scenario: Printed B and C totals are checkable
- **WHEN** the ground-truth line amounts of any synthetic Factura B or C are summed
- **THEN** they equal its ground-truth total exactly

#### Scenario: Factura C issuer
- **WHEN** ground truth is written for any synthetic Factura C
- **THEN** its issuer VAT condition is `responsable_monotributo`, its items have no VAT rate, and the document prints "Responsable Monotributo" in the issuer header

### Requirement: Field-by-field verification against the clean document

Before ground truth is written, every non-null leaf value of an in-domain invoice SHALL be formatted as it is printed (for example amounts as "338.650,00", dates as "12/08/2026", CUITs as "30-71234567-1") and SHALL be found in the text layer of the clean rendered PDF. The entries of `vat_breakdown` SHALL also appear in the text layer in the same order as in the ground truth. Values that are not printed by convention (`currency` without a printed label) SHALL be listed as skipped. A document with any value not found, or with `vat_breakdown` out of printed order, SHALL fail generation. The number of checked fields, the skipped fields and the result SHALL be recorded in the manifest.

#### Scenario: Value not printed
- **WHEN** a ground truth value is not found in the clean PDF text in its printed format
- **THEN** generation of that document fails and names the field

#### Scenario: VAT lines out of printed order
- **WHEN** a ground truth lists the 21% VAT line before the 10.5% line and the document prints 10.5% first
- **THEN** generation of that document fails and names `vat_breakdown`

#### Scenario: Check recorded
- **WHEN** a document passes verification
- **THEN** its manifest entry records how many fields were checked, which were skipped, and that it passed
