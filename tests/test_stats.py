import pytest

from invoice_extractor.evaluation.stats import mcnemar_exact, wilson_interval


# Reference values: n=10 rows are the standard published Wilson 95% table; the k=27, n=30 row is
# worked by hand from the formula (center 0.8546, half-width 0.1108).
@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [
        (5, 10, 0.2366, 0.7634),
        (0, 10, 0.0, 0.2775),
        (10, 10, 0.7225, 1.0),
        (50, 100, 0.4038, 0.5962),
        (27, 30, 0.7437, 0.9654),
    ],
)
def test_wilson_matches_reference_values(k, n, low, high):
    got_low, got_high = wilson_interval(k, n)
    assert got_low == pytest.approx(low, abs=1e-3)
    assert got_high == pytest.approx(high, abs=1e-3)


def test_wilson_stays_inside_the_unit_interval_at_the_extremes():
    assert wilson_interval(0, 30)[0] == 0.0
    assert wilson_interval(30, 30)[1] == 1.0


@pytest.mark.parametrize(("k", "n"), [(1, 0), (0, 0), (-1, 5), (6, 5)])
def test_wilson_rejects_impossible_counts(k, n):
    with pytest.raises(ValueError):
        wilson_interval(k, n)


def test_mcnemar_reference_p_values():
    assert mcnemar_exact(0, 5) == pytest.approx(2 / 32)
    assert mcnemar_exact(1, 9) == pytest.approx(22 / 1024)
    assert mcnemar_exact(2, 8) == pytest.approx(112 / 1024)


def test_mcnemar_is_symmetric_and_one_when_balanced():
    assert mcnemar_exact(3, 7) == mcnemar_exact(7, 3)
    assert mcnemar_exact(4, 4) == 1.0
    assert mcnemar_exact(0, 0) == 1.0


def test_mcnemar_rejects_negative_counts():
    with pytest.raises(ValueError):
        mcnemar_exact(-1, 3)


def test_percentile_is_nearest_rank():
    from invoice_extractor.evaluation.stats import percentile

    values = list(range(1, 31))  # 1..30, deliberately unsorted below
    assert percentile(values[::-1], 0.5) == 15
    assert percentile(values, 0.95) == 29
    assert percentile(values, 1.0) == 30
    assert percentile(values, 0.0) == 1
    assert percentile([7], 0.95) == 7


def test_percentile_rejects_empty_sample_and_bad_q():
    from invoice_extractor.evaluation.stats import percentile

    with pytest.raises(ValueError):
        percentile([], 0.5)
    with pytest.raises(ValueError):
        percentile([1], 1.5)
