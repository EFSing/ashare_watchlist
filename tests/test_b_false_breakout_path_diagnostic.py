import numpy as np
import pandas as pd
import pytest

from b_false_breakout_path_diagnostic import path_features, label_state, contrast, analyze
from test_b_phase_volume_path_diagnostic import _fixture
from track_perf import rebuild_execution_state_from_observations
from trading_calendar import TradingCalendar


def test_defense_uses_exact_level_and_excludes_signal_day():
    close, volume, high, low, dates = _fixture()
    close[64] = 9.7
    close[65] = 10.0
    low[64] = 9.5
    low[-1] = 8.0
    feature = path_features(close, volume, high, low, dates)
    assert feature['base_hi'] == 10.0
    assert feature['min_low_vs_breakout_level'] == pytest.approx(-.05)
    assert feature['min_close_vs_breakout_level'] == pytest.approx(-.03)
    assert feature['max_retest_depth_vs_breakout_level'] == pytest.approx(.05)
    assert feature['days_below_breakout_level'] == 1
    assert feature['reclaim_breakout_level_days'] == 1
    assert feature['days_to_reclaim_breakout_level'] == 1
    assert feature['breakout_volume_ratio'] == 2
    assert feature['days_from_breakout_to_signal'] == 7


def test_empty_retest_and_unreclaimed_breach_are_missing_not_fabricated():
    feature = path_features(*_fixture(breakout_index=68))
    assert feature['min_close_vs_breakout_level'] is None
    assert feature['exceeds_retest_local_high'] is None
    assert feature['feature_unavailable']['min_close_vs_breakout_level'] == 'NO_PRE_T_RETEST_INTERVAL'
    close, volume, high, low, dates = _fixture()
    close[63:] = 9.9
    feature = path_features(close, volume, high, low, dates)
    assert feature['reclaim_breakout_level_days'] is None
    assert feature['feature_unavailable']['reclaim_breakout_level_days'] == 'NOT_RECLAIMED'


def test_reactivation_reference_is_pre_t_high_and_return_is_separate():
    close, volume, high, low, dates = _fixture()
    close[-1] = 10.4
    high[-1] = 12
    feature = path_features(close, volume, high, low, dates)
    assert feature['exceeds_retest_local_high'] is True
    assert feature['days_to_reactivation_local_high'] == 6
    assert feature['reactivation_price_strength'] == pytest.approx(10.4/10.1-1)
    high[65] = 10.8
    assert path_features(close, volume, high, low, dates)['exceeds_retest_local_high'] is False


def test_formal_replay_t1_fast_stop_and_ambiguity_labels():
    cal = TradingCalendar(holidays=[])
    observations = [dict(date=d,open=10,high=12,low=8,price=10) for d in ('2024-01-03','2024-01-04')]
    signal = dict(date='2024-01-02',trigger=10,stop=9,target=11,observations=observations)
    state = rebuild_execution_state_from_observations(signal,cal,'2024-01-04')
    assert state['entry_day_stop_touched'] is True
    assert label_state(state,{'2024-01-03':1,'2024-01-04':2}) == 'AMBIGUOUS'
    observations[-1].update(open=8,high=8.5,low=7)
    state = rebuild_execution_state_from_observations(signal,cal,'2024-01-04')
    assert label_state(state,{'2024-01-03':1,'2024-01-04':2}) == 'FAST_STOP'
    assert state['entry_price'] == 10
    assert state['exit_price'] == 8


def test_primary_denominator_excludes_nonfast_stop_and_sparse_pairs():
    rows = []
    for defense, target, fast, stop in ((1,10,30,100),(3,30,10,100)):
        for label,n in [('TARGET',target),('FAST_STOP',fast),('STOP',stop)]:
            rows.extend(dict(defense=defense,volume=1,label=label,weight=1.) for _ in range(n))
    frame = pd.DataFrame(rows)
    assert contrast(frame,'defense',1,3,['volume'])['delta_pp'] == -50
    assert contrast(frame,'defense',1,3,['volume'],True)['delta_pp'] == pytest.approx(-100/7)
    assert contrast(frame.iloc[:20],'defense',1,3,['volume'])['state'] == 'INSUFFICIENT_DATA'


def test_unknown_board_limit_proxy_is_unavailable_in_sensitivity():
    features = path_features(*_fixture())
    rows = [dict(**features, symbol=symbol, signal_date='2024-01-02', year='2024',
                 board=board, episode=symbol+'|2023-12-20', regime='TREND_UP',
                 label=label, near_price_limit_proxy=proxy)
            for symbol,board,label,proxy in [('600000.sh','main','TARGET',False),
                                             ('830001.bj','OUT_OF_SCOPE_PREFIX','FAST_STOP',None)]]
    result = analyze(pd.DataFrame(rows))
    assert result['sample_counts']['rows'] == 2
    assert result['robustness']['exclude_near_limit_proxy']['counts']['rows'] == 1
    assert result['robustness']['main']['counts']['FAST_STOP'] == 0
