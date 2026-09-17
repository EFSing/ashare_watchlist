from __future__ import annotations

from datetime import date, timedelta
import json

import numpy as np
import pytest

import b_shadow_monitor as shadow
import render_daily_close_html as renderer
from data_paths import DataPaths
from test_b_phase_volume_path_diagnostic import _fixture
from track_perf import _signal_from_candidate, new_tracker
from trading_calendar import TradingCalendar
from watchlist_schema import load_watchlist


CALENDAR = TradingCalendar(holidays={date(2026, 9, 7)})


def _report_candidate(code: str, score: int) -> dict[str, object]:
    return {
        "code": code,
        "name": f"候选{code}",
        "buy_type": "B 突破回踩",
        "score": score,
        "price": 10.0,
        "trigger": 10.2,
        "stop": 9.5,
        "target": 12.0,
        "rr": 2.57,
        "sector": "测试行业",
        "setup": "B_BREAKOUT_RETEST",
    }


def _write_report_inputs(root, candidates: list[dict[str, object]]) -> tuple[DataPaths, dict[str, object]]:
    data_root = root / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": "2026-09-10",
        "mode": "close",
        "market_env": {"grade": "A"},
        "sectors": [],
        "candidates": candidates,
        "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1",
    }
    watchlist_path = data_root / "watchlist_20260910.json"
    watchlist_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    watchlist = load_watchlist(watchlist_path)
    tracker = new_tracker()
    for candidate in watchlist["candidates"]:
        signal = _signal_from_candidate(watchlist, candidate, CALENDAR)
        tracker["signals"][signal["signal_id"]] = signal
    (data_root / "perf_tracker.json").write_text(json.dumps(tracker, ensure_ascii=False), encoding="utf-8")
    return DataPaths(data_root), watchlist


def _index_bars() -> list[dict[str, object]]:
    start = date(2026, 7, 12)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.0 + index,
            "volume": 1000.0,
        }
        for index in range(61)
    ]


def _stock_bars() -> list[dict[str, object]]:
    close, volume, high, low, _dates = _fixture(signal_volume=80.0)
    start = date(2026, 7, 3)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "close": float(close[index]),
            "high": float(high[index]),
            "low": float(low[index]),
            "volume": float(volume[index]),
        }
        for index in range(len(close))
    ]


def _captured_report_fixture(tmp_path):
    paths, watchlist = _write_report_inputs(tmp_path, [_report_candidate("002394", 70)])
    capture = shadow.capture_t_close_signals(
        watchlist_path=paths.watchlist_file("2026-09-10"),
        run_manifest_path=None,
        generation_input_manifest={
            "status": "READY_FOR_STRATEGY_EVALUATION",
            "signal_date": "2026-09-10",
            "input_fingerprint": "a" * 64,
            "index": {"bars": _index_bars()},
            "stock_klines": [{"symbol": "002394", "bars": _stock_bars()}],
        },
        market_env={},
        input_package_sha256="b" * 64,
        store_root=paths.root / "shadow_monitor",
    )
    return paths, watchlist, capture


def test_frozen_volume_observation_matches_pullback_window_and_excludes_signal_day():
    close, volume, high, low, dates = _fixture(signal_volume=80.0)
    close[63:69] = [10.0, 10.2, 10.0, 10.1, 10.1, 10.0]
    volume[63:69] = [80.0, 40.0, 20.0, 60.0, 30.0, 10.0]
    trace = shadow._first_breakout_trace(close, volume, high, low, dates)
    assert trace is not None

    first = shadow._pullback_volume_observation(close, volume, trace)
    volume[-1] = 999.0
    second = shadow._pullback_volume_observation(close, volume, trace)

    assert first["observation_version"] == shadow.VOLUME_OBSERVATION_VERSION
    assert first["window_days"] == 6
    assert first["down_volume_share"] == pytest.approx(110.0 / 240.0)
    assert first["up_down_volume_ratio"] == pytest.approx(50.0 / (110.0 / 3.0))
    assert first["pullback_volume_decay_ratio"] == pytest.approx((60.0 + 30.0 + 10.0) / (80.0 + 40.0 + 20.0))
    assert first["down_volume_share"] == second["down_volume_share"]
    assert first["up_down_volume_ratio"] == second["up_down_volume_ratio"]
    assert first["pullback_volume_decay_ratio"] == second["pullback_volume_decay_ratio"]


@pytest.mark.parametrize(
    ("breakout_index", "pullback_volumes"),
    [
        (62, [100.0, 100.0, 100.0, 50.0, 50.0, 50.0]),
        (63, [100.0, 100.0, 50.0, 50.0, 50.0]),
    ],
)
def test_decay_ratio_uses_frozen_even_and_odd_split(breakout_index, pullback_volumes):
    close, volume, high, low, dates = _fixture(breakout_index=breakout_index)
    volume[breakout_index + 1:-1] = pullback_volumes
    trace = shadow._first_breakout_trace(close, volume, high, low, dates)
    assert trace is not None
    result = shadow._pullback_volume_observation(close, volume, trace)
    assert result["pullback_volume_decay_ratio"] == pytest.approx(0.5)


def test_missing_semantics_are_not_zero_filled():
    close, volume, high, low, dates = _fixture()
    close[63:69] = close[62]
    trace = shadow._first_breakout_trace(close, volume, high, low, dates)
    assert trace is not None
    result = shadow._pullback_volume_observation(close, volume, trace)
    assert result["up_down_volume_ratio"] is None
    assert result["missing_reason"]["up_down_volume_ratio"] == "NO_UP_OR_DOWN_DAY"

    close, volume, high, low, dates = _fixture(breakout_index=66)
    trace = shadow._first_breakout_trace(close, volume, high, low, dates)
    assert trace is not None
    short = shadow._pullback_volume_observation(close, volume, trace)
    assert short["window_days"] == 2
    assert short["pullback_volume_decay_ratio"] is None
    assert short["missing_reason"]["pullback_volume_decay_ratio"] == "PULLBACK_WINDOW_LT_4"


def test_t_close_capture_persists_machine_readable_observation_and_renderer_uses_it(tmp_path):
    paths, watchlist, capture = _captured_report_fixture(tmp_path)
    assert capture["status"] == shadow.CAPTURE_COMPLETE

    store = shadow.load_store(paths.root / "shadow_monitor", missing_ok=False)
    assert store is not None
    signal_id = watchlist["candidates"][0]["signal_id"]
    observation = store["signals"][signal_id]["pre_outcome"]["volume_observation"]
    assert observation["protocol_commit_sha"] == shadow.VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA
    assert set(observation) >= {
        "observation_version", "down_volume_share", "up_down_volume_ratio",
        "pullback_volume_decay_ratio", "missing_reason", "window_days",
    }

    model = renderer.build_report_model("2026-09-10", paths=paths, calendar=CALENDAR)
    row = model.watchlist_rows[0]
    assert row["volume_observation"] == observation
    text = renderer.render_html(model)
    assert "回踩量能" in text
    assert "量能衰减" in text
    assert "下跌日成交量占比" in text
    assert "上涨/下跌日均量比" in text
    assert "回踩后半/前半均量比" in text
    assert "观察指标 · 不参与筛选/排名" in text
    assert "down_volume_share" not in text
    assert "up_down_volume_ratio" not in text
    assert "pullback_volume_decay_ratio" not in text
    assert "市场" not in text
    assert "再启动量能" not in text


def test_report_volume_explanations_and_missing_display_are_neutral():
    observation = {
        "window_days": 6,
        "down_volume_share": 0.533,
        "up_down_volume_ratio": 1.12,
        "pullback_volume_decay_ratio": 0.59,
        "missing_reason": {},
    }
    text = renderer._volume_observations_html(observation)
    assert "当前 53.3%" in text
    assert "上涨日平均成交量约比下跌日高 12%" in text
    assert "当前 0.59×" in text
    assert "量能继续收缩" in text
    assert "观察窗口：6 个交易日" in text

    neutral = renderer._volume_observations_html({
        "window_days": 6,
        "down_volume_share": 0.5,
        "up_down_volume_ratio": 1.0,
        "pullback_volume_decay_ratio": 1.0,
        "missing_reason": {},
    })
    assert "上涨日与下跌日平均成交量接近。" in neutral
    assert "前后半段平均成交量接近。" in neutral

    missing = renderer._volume_observations_html({
        "window_days": 0,
        "down_volume_share": None,
        "up_down_volume_ratio": None,
        "pullback_volume_decay_ratio": None,
        "missing_reason": {
            "down_volume_share": "NO_PULLBACK_WINDOW",
            "up_down_volume_ratio": "NO_PULLBACK_WINDOW",
            "pullback_volume_decay_ratio": "NO_PULLBACK_WINDOW",
        },
    })
    assert missing.count("样本不足") == 3
    assert "0.00×" not in missing and "0.0%" not in missing


def test_observation_does_not_change_candidate_order_or_mobile_layout(tmp_path):
    watchlist = {
        "candidates": [
            {"code": "600002", "name": "低分", "score": 20, "signal_id": "b"},
            {"code": "600001", "name": "高分", "score": 80, "signal_id": "a"},
        ]
    }
    rows = renderer._watchlist_rows(
        watchlist,
        {"signals": {}},
        "2026-09-10",
        {"current_signal_context": {}},
    )
    assert [row["code"] for row in rows] == ["600001", "600002"]
    assert [row["rank"] for row in rows] == [1, 2]

    paths, _watchlist, _capture = _captured_report_fixture(tmp_path)
    model = renderer.build_report_model("2026-09-10", paths=paths, calendar=CALENDAR)
    text = renderer.render_html(model)
    css = text.split("<style>", 1)[1].split("</style>", 1)[0]
    mobile_css = css.split("@media (max-width: 600px)", 1)[1]
    assert ".volume-observations" in mobile_css
    assert "grid-template-columns: 1fr;" in mobile_css
