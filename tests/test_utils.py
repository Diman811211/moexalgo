from moexalgo.utils import CandlePeriod, calc_offset_limit, normalize_period


def test_calc_offset_limit_does_not_cap_large_offsets():
    assert calc_offset_limit(69_000, 10_000) == (69_000, 10_000)


def test_calc_offset_limit_still_caps_limit():
    assert calc_offset_limit(0, 100_000) == (0, 50_000)


def test_quarter_is_a_native_candle_period():
    assert normalize_period(4) == 4
    assert normalize_period(CandlePeriod.ONE_QUARTER) == 4
