from pathlib import Path

import numpy as np
import pytest

import c_bottom_higher_low_early_v1 as study


def history(rows, events=(), sessions=None):
    prices = np.array(rows, dtype=float).T
    days = np.array(sessions if sessions is not None else range(len(rows)))
    scale, offset = study.affine(days, events)
    return study.History(days, days, prices, np.ones(len(days)), scale, offset, (prices - offset) / scale)


def signal(day=0, bar=0, code='600001.sh', pos=.2):
    return study.Signal(code, day, bar, pos, study.Plan(10, 9, 12, 'TEST'))


def test_pre_outcome_lock_normalizes_lf_and_rejects_drift(monkeypatch):
    def committed(root, *args):
        assert args == ('show', f'{study.PROTOCOL_COMMIT}:{study.PROTOCOL}')
        return b'pre-outcome\nlocked\n'

    workspace = b'pre-outcome\r\nlocked\r\n'
    monkeypatch.setattr(study, 'git', committed)
    monkeypatch.setattr(Path, 'read_bytes', lambda _: workspace)
    assert study.verify_protocol(study.ROOT) == study.sha256(b'pre-outcome\nlocked\n').hexdigest()
    workspace += b'extra threshold\r\n'
    with pytest.raises(ValueError, match='PROTOCOL_LOCK_MISMATCH'):
        study.evaluate(study.ROOT)


def test_affine_cash_bonus_allotment_reference_and_causal_anchor():
    proof = study.verify_affine()
    assert proof['draws'] == 500
    assert proof['max_abs_price_error'] < 1e-11
    assert proof['raw_volume_verified']
    dates = np.arange(4)
    scale, offset = study.affine(dates, [(2, .5, .2, .1, 4), (3, 50, 0, 0, 0)])
    assert (scale[1], offset[1]) == (1, 0)
    assert scale[2] * 10 + offset[2] == pytest.approx((10 - .5 + .4) / 1.3)


def test_pair_confirmed_before_t_and_neck_strictly_between_lows(monkeypatch):
    t, left, right = 65, 49, 59
    low = np.full(70, 11.3)
    low[left], low[right] = 10, 10.5
    high = np.full(70, 11.6)
    high[53] = high[54] = 11.8
    close = np.full(70, 11.3)
    pivot_calls = []
    original = study.frozen_c._pivot_indices

    def record(values, radius, *, low):
        pivot_calls.append(values.copy())
        return original(values, radius, low=low)

    monkeypatch.setattr(study.frozen_c, '_pivot_indices', record)
    pair = study.find_pair(high, low, close, t)
    assert pair == (left, 53, right)
    assert pair.left < pair.neck < pair.right <= t - 3 < t
    np.testing.assert_array_equal(pivot_calls[-1], low[t-57:t])
    low[t+1:] = 1
    high[t+1:] = 1000
    assert study.find_pair(high, low, close, t) == pair
    low[right] = 11.3
    low[t-2] = 10.5
    assert study.find_pair(high, low, close, t) is None


def test_target_preserves_legacy_plan_and_corrects_sub_one_r():
    legacy = study.Plan(10, 9, 10.6, 'PRESSURE')
    assert legacy.rr < 1
    corrected = study.corrected_target(legacy)
    assert (corrected.trigger, corrected.stop, corrected.target, corrected.rr) == (10, 9, 12.5, 2.5)
    assert study.corrected_target(study.Plan(10, 9, 9.8, 'PRESSURE')).target == 12.5
    assert study.planned_target(10, 9, 12).source == 'PRESSURE'
    assert study.planned_target(10, 9, 11.99).source == 'TREND_2_5R'


def test_legacy_short_prefix_filter_preserves_frozen_matches():
    rng = np.random.default_rng(7)
    dates = study.replay._date_from_ms
    hits = 0
    for _ in range(32):
        closes = 12 * np.exp(np.cumsum(rng.normal(0, .013, 100)))
        lows, highs = closes * .99, closes * 1.01
        bars = [dict(date=dates(i * 86400000), open=c, high=h, low=l, close=c, volume=1)
                for i, (c, h, l) in enumerate(zip(closes, highs, lows))]
        for config in study.frozen_c.RULE_CANDIDATES.values():
            expected = study.frozen_c.find_pullback_structure(bars, config)['status'] == 'OK'
            assert study.possible_existing_structure(highs, lows, config) == expected
            hits += expected
    assert hits > 0


def test_model_s_gap_limit_locks_t_plus_one_and_cost():
    bars = history([
        (10, 10.5, 9.8, 10),
        (11, 11, 11, 11),
        (10.5, 12.5, 8.8, 9.8),
        (8.82, 8.82, 8.82, 8.82),
        (8.5, 12.5, 8.1, 10),
    ])
    trade = study.settle(signal(), bars, 4)
    assert trade[:3] == ('CLOSED', 2, 4)
    assert trade.net == pytest.approx(8.5 / 10.5 - 1 - .002)
    assert not study.available(9, signal(), trade)
    assert study.available(10, signal(), trade)


def test_model_s_order_expires_on_market_session_ten_during_suspension():
    bars = history([(10, 10, 9.9, 10), (9.5, 9.8, 9.2, 9.5), (10.2, 10.3, 10.1, 10.2)],
                   sessions=[0, 1, 11])
    order = signal()
    assert study.settle(order, bars, 9).status == 'PENDING_AT_CUTOFF'
    trade = study.settle(order, bars, 11)
    assert trade == ('EXPIRED_UNTRIGGERED', None, 10, None)
    assert not study.available(9, order, trade)
    assert study.available(10, order, trade)


def test_settlement_prices_and_fixed_window_follow_cash_action():
    bars = history([(10, 10, 9.9, 10), (10, 10.5, 9.8, 10), (11, 11.4, 10, 10.5)],
                   [(2, 1.0, 0.0, 0.0, 0.0)])
    assert study.settle(signal(), bars, 2).net == pytest.approx(11 / 9 - 1 - .002)
    assert study.fixed_window(signal(), bars, 2) == pytest.approx((10.5 / 9 - 1, 11.4 / 9 - 1, -.02))


def test_same_sellable_bar_two_levels_are_ambiguous():
    bars = history([(10, 10, 9.5, 10), (10, 10.5, 9.6, 10), (10, 12, 9, 10)])
    assert study.settle(signal(), bars, 2) == ('AMBIGUOUS_SAME_BAR', 1, 2, None)


def test_top2_gate_width_and_uses_only_account_state_at_t():
    previous = signal()
    day = 3
    candidates = [signal(day, day, f'60000{i}.sh', i / 10) for i in range(1, 6)]
    sequence = {0: [previous], day: list(reversed(candidates))}
    market = [True, False, False, False], [False, False, False, True]
    results = {previous: study.Trade('CLOSED', 1, 4, .1)}
    assert study.accept(sequence, results, 'G4', 'TOP2', market) == [previous, *candidates[1:3]]
    assert study.accept(sequence, results, 'G2', 'TOP2', market) == [previous]


def test_sealed_and_non_allowlisted_inputs_fail_before_io(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('unexpected Git access')

    monkeypatch.setattr(study, 'git', forbidden)
    for path in ('data/validation/final_oos/summary.json',
                 'data/validation/continuous_speed_probe/probe.json',
                 'data/research/c_rule_funnel_capture_v1/daily/../../unlisted.json'):
        with pytest.raises(ValueError, match='INPUT_PATH_NOT_ALLOWED'):
            study.local_path(study.ROOT, path)
        with pytest.raises(ValueError, match='RUNTIME_PATH_NOT_ALLOWED'):
            study.runtime_blob(study.ROOT, path)
