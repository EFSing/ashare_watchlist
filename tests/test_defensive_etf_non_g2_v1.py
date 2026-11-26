from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import defensive_etf_non_g2_v1 as study
import fetch_defensive_etf_validation_inputs as fetch


def fund(opens, *, dividends=None, payments=None):
    prices = np.column_stack([opens, np.ones(len(opens)), np.ones(len(opens))])
    cash = np.zeros_like(prices)
    for day, dividend in (dividends or {}).items():
        cash[day, 0] = dividend
    eligible = np.tile([True, False, False], (len(prices), 1))
    return study.ETFData(prices, prices.copy(), cash, payments or {}, eligible, np.ones_like(prices))


def test_protocol_uses_ancestor_and_exact_committed_bytes(monkeypatch):
    root = study.ROOT
    local_bytes = b"frozen\r\nprotocol\r\n"
    calls = []

    def check_ancestor(command, **kwargs):
        calls.append(command)
        assert kwargs == {"cwd": root, "check": True, "capture_output": True}

    def committed(command, **kwargs):
        calls.append(command)
        assert kwargs == {"cwd": root}
        return b"frozen\nprotocol\n"

    def local_path(cwd, relative):
        assert (cwd, relative) == (root, study.PROTOCOL)
        return SimpleNamespace(read_bytes=lambda: local_bytes)

    monkeypatch.setattr(study, "allowed_path", local_path)
    monkeypatch.setattr(study.subprocess, "run", check_ancestor)
    monkeypatch.setattr(study.subprocess, "check_output", committed)
    assert study.verify_protocol(root) == b"frozen\nprotocol\n"
    assert calls == [
        ["git", "merge-base", "--is-ancestor", study.PROTOCOL_COMMIT, "HEAD"],
        ["git", "show", f"{study.PROTOCOL_COMMIT}:{study.PROTOCOL}"],
    ]
    local_bytes = b"drift\n"
    with pytest.raises(ValueError, match="differs"):
        study.verify_protocol(root)

    def missing_ancestor(command, **_kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(study.subprocess, "run", missing_ancestor)
    with pytest.raises(ValueError, match="ancestor"):
        study.verify_protocol(root)


@pytest.mark.parametrize("path", [
    "../escaped.json", "D:/Temp/escaped.json", "data/validation/continuous_speed_probe/never_read.json",
    study.ETF_RAW + "/../raw/511260_SH_nav.json", study.ETF_RAW + "/unregistered.json",
])
def test_rejects_input_path_before_filesystem_access(path):
    with pytest.raises(ValueError, match="allowlist"):
        study.allowed_path(study.ROOT, path)


def test_input_hash_mismatch_stops_before_json_decode(monkeypatch):
    name = study.REGISTRY
    monkeypatch.setattr(study, "INPUTS", {name})
    size = len((study.ROOT / name).read_bytes().replace(b"\r\n", b"\n"))
    protocol = f"| `{name}` | {size} | `{'0' * 64}` |\n".encode()
    with pytest.raises(ValueError, match="input identity mismatch"):
        study.verify_inputs(study.ROOT, protocol)


def test_causal_affine_never_transforms_with_a_later_event():
    raw = np.array([100.0, 101.0, 91.0, 92.0, 83.0])
    cumulative = np.array([0, 0, 10, 10, 20])
    np.testing.assert_array_equal(study.causal_prices(raw, cumulative, 1, 2), [100, 101])
    np.testing.assert_array_equal(study.causal_prices(raw, cumulative, 2, 3), [90, 91, 91])
    np.testing.assert_array_equal(study.causal_prices(raw, cumulative, 3, 4), [90, 91, 91, 92])
    assert raw[2] - study.causal_prices(raw, cumulative, 2, 2)[0] == raw[2] - raw[1] + 10


def test_r1_enters_after_three_closes_and_exits_at_first_g2_next_open():
    g2 = np.array([False, False, False, True, True, True])
    r0, r1 = study.defensive_modes(np.r_[True, True, g2])
    assert r0.tolist() == [True, True, True, False, False, False]
    assert r1.tolist() == [False, False, True, False, False, False]
    etf = fund([100, 100, 100, 110, 121, 130])
    values, audit = study.portfolio(etf, g2, None, active=r1, weeks=[False] * len(g2), allocation=2)
    np.testing.assert_allclose(values, [1, 1, 1, 1, 1.1, 1.1])
    assert audit["scheduled_trades"] == audit["forced_exits"] == 1


def test_g2_exit_releases_cash_for_all_six_b_slots():
    codes = [f"code-{i}" for i in range(study.SLOTS)]
    tape = [study.BDay(), study.BDay(occupied_at_close=6),
            study.BDay(order_count=6, entries=codes, close_marks=dict.fromkeys(codes, 1.0), occupied_at_close=6)]
    g2 = [False, True, True]
    etf = fund([100, 100, 110])
    values, audit = study.portfolio(etf, g2, tape, active=[True, False, False], weeks=[False] * 3, allocation=2)
    assert audit["b_buys"] == 6
    assert audit["max_b_etf_cash_overlap"] == 0
    assert audit["etf_value_at_cutoff"] == 0
    assert values[-1] == pytest.approx(1.1 * (1 - study.B_SIDE) / (1 + study.B_SIDE))
    impossible = [tape[0], tape[1], study.BDay(order_count=6, entries=codes,
                                              close_marks=dict.fromkeys(codes, 1.0), occupied_at_close=7)]
    with pytest.raises(ValueError, match="six-slot"):
        study.portfolio(etf, g2, impossible)
    with pytest.raises(ValueError, match="share opening cash"):
        study.portfolio(etf, [False] * 3, tape, active=[True] * 3, weeks=[False] * 3, allocation=2)


def test_only_unoccupied_b_risk_budget_goes_to_etf():
    tape = [study.BDay(order_count=2, entries=["B1", "B2"], close_marks={"B1": 1, "B2": 1}, occupied_at_close=2),
            study.BDay(open_marks={"B1": 1, "B2": 1}, close_marks={"B1": 1, "B2": 1}, occupied_at_close=2)]
    values, audit = study.portfolio(fund([100, 100]), [False, False], tape, active=[True, True], weeks=[False, False], allocation=2)
    assert audit["etf_value_at_cutoff"] == pytest.approx(values[0] * 4 / 6)


def test_b_pending_order_waits_for_g2_before_filling():
    prices = np.array([[9, 9.5, 8.9, 9.3], [9, 9.5, 8.9, 9.3], [10.5, 11, 10, 11],
                       [10.8, 11, 10, 11], [12.5, 13, 12, 12.8]])
    stock = study.Stock(prices, np.ones(5), np.zeros(5), dict(enumerate(range(5))))
    order = study.Order(0, 10, 8, 12)
    tape, counts = study.b_tape({"B": stock}, [[("B", order)], [], [], [], []],
                                [True, False, True, True, True], constrained=True)
    assert [day.entries for day in tape] == [[], [], [], ["B"], []]
    assert tape[2].occupied_at_close == 1 and tape[2].order_count == 0
    assert counts["closed"] == 1 and set(tape[4].open_sales) == {"B"}


@pytest.mark.parametrize("side_cost", [0.00025, 0.00050])
def test_uses_each_side_cost_on_actual_turnover(side_cost):
    etf = fund([100, 100, 120])
    values, audit = study.portfolio(etf, [False, True, True], None, active=[True, False, False],
                                    weeks=[False] * 3, allocation=2, side_cost=side_cost)
    buy_notional = 1 / (1 + side_cost)
    sell_notional = buy_notional * 1.2
    assert values[-1] == pytest.approx(sell_notional * (1 - side_cost))
    assert audit["etf_turnover"] == pytest.approx(buy_notional + sell_notional)
    assert audit["etf_fees"] == pytest.approx((buy_notional + sell_notional) * side_cost)


def test_dividend_preserved_on_ex_date_even_if_opening_trade_sells():
    etf = fund([100, 100, 90, 90], dividends={2: 10}, payments={(2, 0): 3})
    values, audit = study.portfolio(etf, [False, True, True, True], None, active=[True, False, False, False],
                                    weeks=[False] * 4, allocation=2)
    np.testing.assert_allclose(values, np.ones(4))
    assert audit["cash_dividend_accrued"] == pytest.approx(0.10)
    assert audit["outstanding_dividend_at_cutoff"] == 0


def test_approved_growth_factor_check_handles_zero_net_returns():
    assert len(fetch.sessions()) == 1032
    calendar = fetch.sessions()
    prices = [{"date": day, "volume": 1} for day in calendar]
    nav = [{"nav_date": day, "unit_nav": 1, "adj_nav": 2} for day in calendar]
    result = fetch.validate(prices, [], nav, calendar)
    assert result["passed"] and result["nav_return_ratio_undefined"] == len(calendar) - 1
    nav[-1]["adj_nav"] = 4
    assert not fetch.validate(prices, [], nav, calendar)["passed"]


def test_fund_inputs_drop_out_of_bounds_before_reading_payload(monkeypatch):
    monkeypatch.setattr(fetch, "fund_items", lambda *_: [
        {"ex_dividend_date": "2026-08-29"}, {"ex_dividend_date": "2022-05-31"},
    ])
    assert fetch.fetch_dividends(fetch.SYMBOLS[0], "test-key") == []
    monkeypatch.setattr(fetch, "fund_items", lambda *_: [{"nav_date": "2026-08-29"}])
    assert fetch.fetch_nav(fetch.SYMBOLS[0], "test-key") == []
