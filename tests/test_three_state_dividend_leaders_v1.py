import subprocess

import numpy as np
import pytest

import three_state_dividend_leaders_v1 as replay


@pytest.fixture(scope="module")
def prior():
    blobs = {
        replay.FETCH_SOURCE: replay.git(replay.ROOT, "show", f"{replay.ETF_LOCK}:{replay.FETCH_SOURCE}"),
        replay.REPLAY_SOURCE: replay.git(replay.ROOT, "show", f"{replay.ARCHIVE}:{replay.REPLAY_SOURCE}"),
    }
    return replay.load_archive(blobs)


def test_preregistration_is_an_ancestor_and_input_set_is_frozen(monkeypatch):
    inputs, _, protocol_hash = replay.verify_inputs(replay.ROOT)
    assert len(inputs) == 19
    assert len(protocol_hash) == 64
    monkeypatch.setattr(replay, "PROTOCOL_COMMIT", "0" * 40)
    with pytest.raises(subprocess.CalledProcessError):
        replay.verify_inputs(replay.ROOT)


def test_dividends_use_prior_calendar_years_and_only_strictly_later_known_splits():
    stamp = replay.core._ms_from_date
    ex = np.array([stamp(day) for day in (
        "2024-06-01", "2024-07-01", "2025-05-01", "2026-04-01", "2026-06-01", "2026-09-01",
    )])
    years = np.array([2024, 2024, 2025, 2026, 2026, 2026])
    cash = np.array([2.0, 0, 1.5, 0, 1.0, 0])
    factors = np.array([3.0, 2.0, 1.5, 2.0, 1.0, 5.0])
    sessions = np.array([stamp(day) for day in ("2025-12-31", "2026-03-31", "2026-04-01", "2026-08-28")])
    actual = replay.dividend_yield(ex, years, cash, factors, sessions, np.full(len(sessions), 10.0))
    assert actual == pytest.approx([0, (2 / 2 / 1.5 + 1.5) / 20, (2 / 2 / 1.5 + 1.5) / 40,
                                    (2 / 2 / 1.5 + 1.5) / 40])


def test_state_confirms_three_non_strong_days_and_honors_exact_width_floor():
    g2 = np.array([False, False, True, True, False, False, True, False])
    market = {"breadth_n": np.full(8, 20), "above_ma20": np.array([12, 12, 9, 8, 10, 10, 10, 9]),
              "pool_n": np.array([15, 15, 15, 15, 15, 15, 15, 14]), "trend_n": np.full(8, 6)}
    _, _, w45 = replay.states(g2, market, 0.45)
    _, _, w50 = replay.states(g2, market, 0.50)
    assert w45.tolist() == [replay.STRONG, replay.BUFFER, replay.BUFFER, replay.HUG, replay.STRONG, replay.BUFFER]
    assert w50.tolist() == [replay.HUG, replay.HUG, replay.HUG, replay.HUG, replay.STRONG, replay.BUFFER]
    market["pool_n"][5] = 14
    assert replay.states(g2, market, 0.45)[2][3] == replay.DEFENSE


def stock(prior, bars):
    length = len(bars)
    return prior.Stock(np.array(bars, dtype=float), np.ones(length), np.zeros(length), {i: i for i in range(length)})


def test_locked_dividend_buy_and_conditional_strong_open_slot_handoff(prior):
    stuck = stock(prior, [[10, 10.2, 9.8, 10], [9, 9, 9, 9], [8.1, 8.1, 8.1, 8.1],
                          [7.29, 7.29, 7.29, 7.29], [7.1, 7.5, 7, 7.3]])
    liquid = stock(prior, [[10, 11, 9.8, 10]] * 5)
    labels = [replay.HUG, replay.HUG, replay.STRONG, replay.STRONG, replay.STRONG]
    b_ranked = [[], [], [("b", prior.Order(2, 10, 8, 12))], [], []]
    div_ranked = [[(-2, -0.05, "stuck", True), (-1, -0.04, "liquid", True)], [], [], [], []]
    b, div = replay.shared_tape(prior, {"b": liquid}, b_ranked, {"stuck": stuck, "liquid": liquid},
                                div_ranked, labels, [False] * 5, "X1", slots=2)
    assert div[1].entries == ["stuck", "liquid"]
    assert not div[1].open_sales
    assert div[3].open_sales == {"liquid": 1}
    assert div[3].close_marks.keys() == {"stuck"}
    assert b[3].entries == ["b"]
    assert div[4].open_sales == {"stuck": pytest.approx(7.1 / 9)}


def test_x2_same_bar_stop_and_time_exit(prior):
    data = stock(prior, [[10, 10.2, 9.8, 10], [10, 11.5, 9.3, 10.3], [10, 10.2, 9.8, 10.1]])
    trade = replay.DividendPosition(0, 0, 10)
    assert replay.dividend_exit(data, trade, 0, 0, "X2") is None
    assert replay.dividend_exit(data, trade, 1, 1, "X2") == ("late", 9.5, "AMBIGUOUS_SAME_BAR_STOP")
    assert replay.dividend_exit(data, trade, 24, 2, "X2") is None
    assert replay.dividend_exit(data, trade, 25, 2, "X2") == ("late", 10.1, "TIME_EXIT_CLOSE")
    assert replay.dividend_exit(data, trade, 25, None, "X2") is None
    assert replay.dividend_exit(data, trade, 26, 2, "X2") == ("open", 10, "OPEN_EXIT")


def test_etf_funding_releases_cash_for_two_dividend_slots_and_reconciles(prior):
    quotes = np.ones((4, 2))
    etf = prior.ETFData(quotes, quotes, np.zeros_like(quotes), {}, quotes.astype(bool), np.zeros_like(quotes))
    div = [
        replay.DividendDay(),
        replay.DividendDay(),
        replay.DividendDay(entries=["d1", "d2"], close_marks={"d1": 1, "d2": 1}),
        replay.DividendDay(open_marks={"d1": 1.1, "d2": 1.1}, open_sales={"d1": 1.1, "d2": 1.1}),
    ]
    nav, pnl, audit = replay.portfolio(
        prior, etf, [False] * 4, [True] * 4, [False] * 4, [prior.BDay()] * 4, div, side=0.00025, resize=True,
    )
    assert audit["peak_open_stock_slots"] == audit["dividend_buys"] == 2
    assert audit["ending_stock_slots"] == audit["max_cash_overlap"] == 0
    assert audit["minimum_cash"] >= 0
    assert pnl[2, 1] < 0 < pnl[3, 1]
    assert pnl.sum(axis=1) == pytest.approx(np.diff(np.r_[1.0, nav]))


def test_bootstrap_keeps_pairs_and_preferred_candidate_order():
    returns = np.linspace(0.001, 0.005, 100)
    masks = {"2023": np.arange(100) < 50, "2026": np.arange(100) >= 50}
    assert replay.bootstrap_daily(np.zeros(100)) == [0, 0]
    assert replay.bootstrap_weak(returns, returns, masks) == [0, 0]
    assert min(replay.bootstrap_weak(returns, returns - 0.001, masks)) > 0
    selection = replay.choose(["S2_W50_X1", "S2_W45_X1"], {
        "S2_W50_X1": {"status": "ADOPT"}, "S2_W45_X1": {"status": "ADOPT"},
    })
    assert selection["selected"] == "S2_W50_X1"
