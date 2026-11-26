from hashlib import sha256
from pathlib import Path
import subprocess

import numpy as np
import pytest

import weak_regime_panic_reversion_v1 as study


def stock(bars, sessions=None):
    prices = np.array(bars, dtype=float)
    length = len(prices)
    return study.Stock(np.arange(length), prices, np.full(length, 10_000_000.0),
                       np.full(length, 90_000_000.0), np.ones(length), np.zeros(length),
                       dict(zip(range(length) if sessions is None else sessions, range(length))))


def replay(stocks, candidates, policy="X1", mode="TOP2"):
    return study.replay(stocks, candidates, np.ones(len(candidates), dtype=bool), policy, mode)


def test_protocol_lock_accepts_only_lf_normalized_commit_bytes(monkeypatch):
    path = study.ROOT / study.PROTOCOL
    original = Path.read_bytes
    canonical = study.lf(original(path))
    commit = study.PROTOCOL_COMMIT

    def require_history(args, **kwargs):
        assert args == ["git", "merge-base", "--is-ancestor", commit, "HEAD"]
        assert kwargs == {"cwd": study.ROOT, "check": True, "capture_output": True}

    def read_git(args, **kwargs):
        assert args == ["git", "show", f"{commit}:{study.PROTOCOL}"]
        assert kwargs == {"cwd": study.ROOT}
        return canonical

    # CI uses a shallow checkout. The two full replays exercise Git against real history.
    monkeypatch.setattr(subprocess, "run", require_history)
    monkeypatch.setattr(subprocess, "check_output", read_git)
    monkeypatch.setattr(Path, "read_bytes", lambda self: canonical.replace(b"\n", b"\r\n") if self == path else original(self))
    assert study.verify_protocol(study.ROOT) == sha256(canonical).hexdigest()
    monkeypatch.setattr(Path, "read_bytes", lambda self: canonical + b"\n" if self == path else original(self))
    with pytest.raises(RuntimeError, match="PROTOCOL_DRIFT"):
        study.verify_protocol(study.ROOT)


@pytest.mark.parametrize("path", [
    "data/validation/continuous_speed_probe/sample.json",
    "data/validation/final_oos/sample.parquet",
    study.RAW + "../raw/daily_k.parquet",
])
def test_rejects_outside_allowlist_before_resolving_path(path, monkeypatch):
    def forbidden(_path):
        pytest.fail("out-of-scope path was resolved")

    monkeypatch.setattr(Path, "resolve", forbidden)
    with pytest.raises(RuntimeError, match="outside research allowlist"):
        study.allowed_path(study.ROOT, path)


def test_allowlisted_input_cannot_redirect(monkeypatch):
    path = study.ROOT / (study.RAW + "daily_k.parquet")
    original = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda self: study.ROOT / "unexpected.parquet"
                        if self == path else original(self))
    with pytest.raises(RuntimeError, match="redirects"):
        study.allowed_path(study.ROOT, study.RAW + "daily_k.parquet")


def test_affine_matches_reference_with_off_session_event_and_excludes_future():
    n = 260
    close = np.linspace(80, 100, n)
    s = stock(np.column_stack([close - 0.2, close + 0.3, close - 0.4, close]))
    s.dates *= 2
    events = [(11, 0.06, 0.15, 0.12, 21.0), (180, 0.16, 0.2, 0.02, 5.0),
              (280, 0.3, 0.0, 0.0, 0.0), (502, 0.9, 0.23, 0.08, 6.0)]
    s.scale, s.offset = study.affine(s.dates, events)
    names = ("open", "high", "low", "close")
    raw = {"date_ms": s.dates, "date_text": {d: str(d) for d in s.dates}, "volume": s.volume,
           **{name: s.ohlc[:, i] for i, name in enumerate(names)}}
    anchor = 249
    expected = study.reference._adjusted_bars(raw, 0, anchor + 1, events, s.dates[anchor])
    np.testing.assert_allclose(s.prices(anchor, 0), [[line[k] for k in names] for line in expected], rtol=0, atol=1e-11)
    truncated = study.affine(s.dates, events[:-1])
    np.testing.assert_array_equal(s.scale[:anchor + 1], truncated[0][:anchor + 1])
    np.testing.assert_array_equal(s.offset[:anchor + 1], truncated[1][:anchor + 1])
    assert expected[90]["close"] == pytest.approx(s.convert(s.ohlc[90, 3], 90, anchor))


def test_t1_no_reschedule_for_limit_up_or_suspension_but_buys_limit_down_and_waits_to_sell():
    a = stock([(10, 10, 10, 10), (11, 11, 11, 11), (11, 12, 10, 11), (11, 11, 10, 10)])
    b = stock([(10, 10, 10, 10), (9, 9, 9, 9), (8.1, 8.1, 8.1, 8.1), (7.8, 8.2, 7.7, 8)])
    c = stock([(10, 10, 10, 10), (12, 13, 11, 12)], sessions=[0, 2])
    rows, pnl, peak = replay({"a": a, "b": b, "c": c}, [["a", "b", "c"], [], [], []], mode="S_ALL")
    assert [r.status for r in rows[:2]] == ["UNBUYABLE_SKIP", "UNBUYABLE_SKIP"]
    assert rows[2].status == "LOCKED_EXIT_NEXT_OPEN"
    assert rows[2].exit == 3
    assert rows[2].net == pytest.approx((7.8 / 9 - 1) * 100 - 0.2)
    assert pnl.sum() == pytest.approx(rows[2].net)
    assert peak == 1


def test_x1_same_bar_both_hits_counts_as_stop_only_in_pessimistic_stats():
    s = stock([(10, 10, 10, 10), (10, 12, 8, 10), (10, 11, 9, 10)])
    rows, pnl, _ = replay({"a": s}, [["a"], [], []])
    assert rows[0].status == study.AMBIGUOUS
    assert rows[0].exit == 2
    metrics = study.trade_metrics(rows)
    assert metrics["net_avg_return_pct"] is None
    assert metrics["closed"] == 0
    assert metrics["ambiguous_rate_pct"] == 100
    assert metrics["pessimistic_net_avg_pct"] == pytest.approx(-5.2)
    assert pnl.sum() == pytest.approx(-5.2)


def test_x2_reclaims_on_buy_day_and_uses_next_open_even_if_next_close_is_lower():
    bars = [(10, 10, 10, 10)] * 5 + [(10, 12, 9, 11), (11.5, 11.6, 9, 9.2)]
    candidates = [[] for _ in bars]
    candidates[4] = ["a"]
    rows, _, _ = replay({"a": stock(bars)}, candidates, policy="X2")
    assert rows[0].status == "MA5_NEXT_OPEN"
    assert rows[0].exit == 6
    assert rows[0].net == pytest.approx(14.8)
    bars[5] = (10, 12, 9, 9.2)
    rows, _, _ = replay({"a": stock(bars)}, candidates, policy="X2")
    assert rows[0].status == "STOP"
    assert rows[0].net == pytest.approx(-6.2)


def test_x2_timeout_executes_at_open_before_intraday_stop():
    bars = [(10, 10, 10, 10)] * 5 + [(10, 10, 9.5, 9.5), (9.8, 9.9, 9.5, 9.5),
                                      (9.8, 9.9, 9.5, 9.5), (9.8, 9.9, 9.5, 9.5),
                                      (9.8, 9.9, 9.5, 9.5), (9.9, 10, 8, 8.5)]
    # A strictly falling close keeps the MA5 condition false until the hard deadline.
    for i, c in enumerate([9.8, 9.7, 9.6, 9.5, 9.49], 5):
        bars[i] = (10, 10, c, c)
    candidates = [[] for _ in bars]
    candidates[4] = ["a"]
    rows, _, _ = replay({"a": stock(bars)}, candidates, policy="X2")
    assert rows[0].status == "TIME_EXIT_OPEN"
    assert rows[0].net == pytest.approx(-1.2)


def test_top2_caps_at_six_and_cooldown_waits_three_full_sessions():
    candidates = [["a", "b", "z"], ["c", "d", "z"], ["e", "f", "z"], ["z"],
                  ["z"], ["a"], ["a"], ["a"], ["a"], ["a"], [], [], [], [], []]
    stocks = {c: stock([(10, 10, 10, 10)] * len(candidates)) for c in "abcdefz"}
    rows, _, peak = replay(stocks, candidates)
    assert peak == 6
    assert sorted(r.signal for r in rows) == [0, 0, 1, 1, 2, 2, 9]
    assert all(r.status == "TIME_EXIT_CLOSE" for r in rows)


def test_unresolved_locked_position_is_marked_but_not_treated_as_closed():
    s = stock([(10, 10, 10, 10), (10, 10, 10, 10), (9, 9, 9, 9)])
    rows, pnl, _ = replay({"a": s}, [["a"], [], []])
    assert rows[0].status == "OPEN_AT_CUTOFF"
    assert study.trade_metrics(rows)["closed"] == 0
    assert pnl.sum() == pytest.approx(-10.2)
