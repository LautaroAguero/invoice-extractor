from decimal import Decimal

from generator.identifiers import LEGAL_ENTITY_PREFIXES, is_valid_cuit
from generator.params import generate_params


def test_same_seed_gives_equal_parameters():
    a = generate_params(1001, tipo_cbte=1)
    b = generate_params(1001, tipo_cbte=1)
    assert a == b


def test_different_seed_gives_different_parameters():
    a = generate_params(1001, tipo_cbte=1)
    b = generate_params(1002, tipo_cbte=1)
    assert a != b


def test_cuits_are_valid_with_legal_entity_prefix():
    p = generate_params(1001, tipo_cbte=1)
    assert is_valid_cuit(p.issuer.cuit)
    assert p.issuer.cuit[:2] in LEGAL_ENTITY_PREFIXES
    assert is_valid_cuit(p.customer.cuit)
    assert p.customer.cuit[:2] in LEGAL_ENTITY_PREFIXES


def test_many_seeds_always_produce_valid_cuits():
    for seed in range(1001, 1101):
        p = generate_params(seed, tipo_cbte=1)
        assert is_valid_cuit(p.issuer.cuit)
        assert is_valid_cuit(p.customer.cuit)


def test_cae_is_14_digits():
    p = generate_params(1001, tipo_cbte=1)
    assert len(p.cae) == 14
    assert p.cae.isdigit()


def test_totals_close_exactly():
    p = generate_params(1001, tipo_cbte=1)
    expected_total = sum((it.line_amount for it in p.items), Decimal("0.00")) + sum(
        (it.vat_amount for it in p.items), Decimal("0.00")
    )
    assert p.total == expected_total
    # net + vat breakdown reconstructs the same total
    breakdown_vat = sum((amt for _, _, amt in p.vat_breakdown), Decimal("0.00"))
    assert p.net_amount + breakdown_vat == p.total


def test_consumidor_final_unidentified_has_no_customer_party():
    p = generate_params(1001, tipo_cbte=6, consumidor_final_unidentified=True)
    assert p.customer is None


def test_foreign_currency_items_have_no_vat():
    p = generate_params(1001, tipo_cbte=19, currency="USD", exchange_rate=Decimal("875.0000"))
    assert all(it.vat_rate is None for it in p.items)
    assert p.vat_amount == Decimal("0.00")
    assert p.total == sum((it.line_amount for it in p.items), Decimal("0.00"))


def test_factura_b_lines_include_vat_exactly():
    for seed in range(1001, 1051):
        p = generate_params(seed, tipo_cbte=6)
        for it in p.items:
            assert it.vat_rate is not None
            assert it.net_amount + it.vat_amount == it.line_amount
        assert p.total == sum((it.line_amount for it in p.items), Decimal("0.00"))
        assert p.net_amount + p.vat_amount == p.total
        assert sum((base for _, base, _ in p.vat_breakdown), Decimal("0.00")) == p.net_amount


def test_factura_b_vat_is_the_rate_share_of_the_line():
    p = generate_params(1001, tipo_cbte=6)
    for it in p.items:
        expected_net = it.line_amount / (1 + it.vat_rate / Decimal(100))
        assert abs(it.net_amount - expected_net) <= Decimal("0.005")


def test_nota_de_debito_b_prices_like_a_factura_b():
    p = generate_params(1001, tipo_cbte=7)
    assert all(it.vat_included for it in p.items)
    assert p.total == sum((it.line_amount for it in p.items), Decimal("0.00"))


def test_factura_c_has_no_vat():
    p = generate_params(1001, tipo_cbte=11)
    assert all(it.vat_rate is None for it in p.items)
    assert p.vat_amount == Decimal("0.00")
    assert p.vat_breakdown == []
    assert p.total == sum((it.line_amount for it in p.items), Decimal("0.00"))


def test_pricing_keeps_the_random_sequence():
    # Same seed, different letter: the drawn quantities, prices and CAE are the same.
    a, b, c = (generate_params(1001, tipo_cbte=t) for t in (1, 6, 11))
    drawn = [(it.quantity, it.unit_price) for it in a.items]
    assert drawn == [(it.quantity, it.unit_price) for it in b.items]
    assert drawn == [(it.quantity, it.unit_price) for it in c.items]
    assert a.cae == b.cae == c.cae


def test_long_description_item_is_marked():
    p = generate_params(1001, tipo_cbte=1, n_items=3, long_description_item=1)
    assert len(p.items[1].description) > 100
