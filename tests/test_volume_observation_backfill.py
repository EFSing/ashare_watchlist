from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

import b_shadow_monitor as shadow
import volume_observation_backfill as backfill
from test_b_phase_volume_path_diagnostic import _fixture


FIXED_TIME = "2026-09-20T18:00:00+08:00"


def _trading_dates(count: int) -> list[str]:
    result: list[str] = []
    current = date(2026, 9, 18)
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current -= timedelta(days=1)
    return list(reversed(result))


def _bars() -> list[dict[str, float | str]]:
    close, volume, high, low, _dates = _fixture(signal_volume=80.0)
    close[63:69] = [10.0, 10.2, 10.0, 10.1, 10.1, 10.0]
    close[-1] = 10.0
    volume[63:69] = [80.0, 40.0, 20.0, 60.0, 30.0, 10.0]
    dates = _trading_dates(len(close))
    return [
        {
            "date": dates[index],
            "open": float(max(low[index], min(high[index], close[index]))),
            "high": float(high[index]),
            "low": float(low[index]),
            "close": float(close[index]),
            "volume": float(volume[index]),
        }
        for index in range(len(close))
    ]


def _watchlist(tmp_path: Path) -> Path:
    candidates = []
    for index, code in enumerate(backfill.LOCKED_CODES, start=1):
        candidates.append({
            "code": code,
            "name": f"候选{code}",
            "score": 40 + index,
            "price": 10.0,
            "signal_id": f"{backfill.EXPECTED_STRATEGY}:{backfill.TARGET_DATE}:{code}:B_BREAKOUT_RETEST",
        })
    path = tmp_path / "watchlist_20260918.json"
    path.write_text(json.dumps({
        "date": backfill.TARGET_DATE,
        "mode": "close",
        "strategy_version": backfill.EXPECTED_STRATEGY,
        "candidates": candidates,
        "market_env": {},
        "sectors": [],
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
    return path


def _metadata(code: str) -> dict[str, str]:
    return {
        "provider": backfill.EXPECTED_PROVIDER,
        "api": backfill.HITHINK_STOCK_KLINE_API,
        "provider_symbol": backfill._hithink_thscode(code),
        "adjustment": backfill.EXPECTED_ADJUSTMENT,
        "adjustment_mode": backfill.PROVIDER_QFQ_SNAPSHOT,
    }


class _OnlyHistoricalClient:
    def __init__(self, bars_by_code):
        self.bars_by_code = bars_by_code
        self.historical_calls: list[str] = []
        self.universe_calls = 0
        self.snapshot_calls = 0

    def historical_bars(self, thscode, *, start, end, index, timeout):
        assert index is False
        self.historical_calls.append(thscode)
        return self.bars_by_code[thscode.split(".", 1)[0]]

    def universe(self, *args, **kwargs):
        self.universe_calls += 1
        raise AssertionError("universe must not be called")

    def snapshots(self, *args, **kwargs):
        self.snapshot_calls += 1
        raise AssertionError("snapshots must not be called")


def test_fetches_only_locked_symbols_and_reuses_frozen_calculation(tmp_path):
    watchlist = _watchlist(tmp_path)
    bars = _bars()
    client = _OnlyHistoricalClient({code: bars for code in backfill.LOCKED_CODES})
    output = tmp_path / "daily_close_20260918_volume_addendum.html"

    summary = backfill.generate_volume_addendum(
        watchlist,
        output,
        provider_client=client,
        retrieved_at_bjt=FIXED_TIME,
        generated_at_bjt=FIXED_TIME,
    )

    assert client.historical_calls == [backfill._hithink_thscode(code) for code in backfill.LOCKED_CODES]
    assert client.universe_calls == 0
    assert client.snapshot_calls == 0
    assert summary["provider_call_symbols"] == list(backfill.LOCKED_CODES)
    assert summary["candidate_count"] == 10
    assert summary["valid_count"] == 10
    assert [item["code"] for item in summary["candidates"]] == list(backfill.LOCKED_CODES)
    observation = summary["candidates"][0]["observation"]
    assert observation["observation_version"] == shadow.VOLUME_OBSERVATION_VERSION
    assert observation["window_days"] == 6
    assert observation["down_volume_share"] == pytest.approx(110.0 / 240.0)
    assert observation["up_down_volume_ratio"] == pytest.approx(50.0 / (110.0 / 3.0))
    assert observation["pullback_volume_decay_ratio"] == pytest.approx(100.0 / 140.0)
    html = output.read_text(encoding="utf-8")
    assert backfill.RETROSPECTIVE_VOLUME_ENRICHMENT in html
    assert "不参与 Formal B 筛选、Score、排名" in html
    assert "PROSPECTIVE_CAPTURED" in html
    assert not (tmp_path / "shadow_monitor").exists()


def test_missing_one_symbol_is_fail_soft_and_future_bar_is_rejected(tmp_path):
    watchlist = _watchlist(tmp_path)
    bars = _bars()
    missing_code = backfill.LOCKED_CODES[4]
    future_code = backfill.LOCKED_CODES[7]
    calls: list[str] = []

    def fetch(code: str):
        calls.append(code)
        if code == missing_code:
            raise RuntimeError("symbol unavailable")
        if code == future_code:
            future_bar = dict(bars[-1])
            future_bar["date"] = "2026-09-19"
            return [*bars, future_bar], _metadata(code)
        return bars, _metadata(code)

    summary = backfill.generate_volume_addendum(
        watchlist,
        tmp_path / "addendum.html",
        fetch_historical=fetch,
        retrieved_at_bjt=FIXED_TIME,
        generated_at_bjt=FIXED_TIME,
    )

    assert calls == list(backfill.LOCKED_CODES)
    assert summary["valid_count"] == 8
    assert summary["missing_count"] == 2
    by_code = {item["code"]: item for item in summary["candidates"]}
    assert by_code[missing_code]["valid"] is False
    assert by_code[missing_code]["validation_reason"] == "RuntimeError"
    assert by_code[future_code]["valid"] is False
    assert by_code[future_code]["validation_reason"].startswith("FUTURE_DATA_DETECTED")
    assert by_code[backfill.LOCKED_CODES[0]]["valid"] is True


def test_validated_cache_is_reused_repeat_is_byte_stable_and_formal_files_unchanged(tmp_path):
    watchlist = _watchlist(tmp_path)
    bars = _bars()
    cache = tmp_path / "volume_input.json"
    cache.write_text(json.dumps({
        "schema_version": backfill.INPUT_CACHE_SCHEMA_VERSION,
        "target_date": backfill.TARGET_DATE,
        "provider": backfill.EXPECTED_PROVIDER,
        "api": backfill.HITHINK_STOCK_KLINE_API,
        "adjustment": backfill.EXPECTED_ADJUSTMENT,
        "adjustment_mode": backfill.PROVIDER_QFQ_SNAPSHOT,
        "retrieved_at_bjt": FIXED_TIME,
        "stock_klines": [
            {"symbol": code, "bars": bars}
            for code in backfill.LOCKED_CODES
        ],
    }, ensure_ascii=False), encoding="utf-8")
    canonical_files = []
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir()
    for name in (
        "watchlist_20260918.json",
        "daily_checkpoint_20260918.json",
        "daily_close_20260918.html",
        "daily_delivery_20260918.json",
    ):
        path = canonical_dir / name
        path.write_text(f"canonical-{name}", encoding="utf-8")
        canonical_files.append((path, hashlib.sha256(path.read_bytes()).hexdigest()))

    class _MustNotFetch:
        def historical_bars(self, *args, **kwargs):
            raise AssertionError("validated cache should avoid provider calls")

    output = tmp_path / "daily_close_20260918_volume_addendum.html"
    first = backfill.generate_volume_addendum(
        watchlist,
        output,
        cache_path=cache,
        provider_client=_MustNotFetch(),
        retrieved_at_bjt=FIXED_TIME,
        generated_at_bjt=FIXED_TIME,
    )
    first_bytes = output.read_bytes()
    second = backfill.generate_volume_addendum(
        watchlist,
        output,
        cache_path=cache,
        provider_client=_MustNotFetch(),
        retrieved_at_bjt=FIXED_TIME,
        generated_at_bjt=FIXED_TIME,
    )

    assert first["input_cache_status"] == "USED"
    assert second["input_cache_status"] == "USED"
    assert first_bytes == output.read_bytes()
    assert first["output_sha256"] == second["output_sha256"]
    for path, digest in canonical_files:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_canonical_report_path_is_protected(tmp_path):
    watchlist = _watchlist(tmp_path)
    with pytest.raises(backfill.VolumeAddendumError, match="canonical report"):
        backfill.generate_volume_addendum(
            watchlist,
            tmp_path / "daily_close_20260918.html",
            fetch_historical=lambda code: (_bars(), _metadata(code)),
            retrieved_at_bjt=FIXED_TIME,
            generated_at_bjt=FIXED_TIME,
        )


def test_source_has_no_full_market_or_shadow_capture_path():
    source = Path(backfill.__file__).read_text(encoding="utf-8")
    assert "client.universe(" not in source
    assert "client.snapshots(" not in source
    assert "capture_t_close_signals" not in source
    assert "evaluate_numeric_projection" not in source
