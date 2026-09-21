from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re

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


def test_existing_addendum_coverage_refresh_preserves_volume_observations(tmp_path):
    watchlist = _watchlist(tmp_path)
    payload = json.loads(watchlist.read_text(encoding="utf-8"))
    payload["input_coverage"] = {
        "schema_version": "INPUT_COVERAGE_V1",
        "coverage_status": "DEGRADED",
        "evaluated_symbol_count": 3092,
        "excluded_symbol_count": 1,
        "excluded_symbols": [{
            "symbol": "605366",
            "provider_symbol": "605366.SH",
            "target_date": "2026-09-18",
            "provider": "HiThink Financial-API",
            "status": "EXCLUDED_PROVIDER_STALE",
            "reason": "TARGET_DAY_HISTORICAL_STALE",
            "latest_historical_date": "2026-09-17",
            "quote_trade_state": "TRADED",
            "evidence": {"quote": {}, "historical": {}},
            "policy_version": "PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1",
        }],
        "formal_result_valid": True,
        "policy_version": "PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1",
    }
    watchlist.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")
    output = tmp_path / "daily_close_20260918_volume_enriched.html"
    backfill.generate_volume_addendum(
        watchlist,
        output,
        fetch_historical=lambda code: (_bars(), _metadata(code)),
        original_artifacts={"watchlist_sha256": hashlib.sha256(watchlist.read_bytes()).hexdigest()},
        retrieved_at_bjt=FIXED_TIME,
        generated_at_bjt=FIXED_TIME,
    )
    old_block = (
        '<div class="review-callout warning"><strong>INPUT COVERAGE = DEGRADED</strong>'
        '<p>excluded symbol = 605366；reason = TARGET_DAY_HISTORICAL_STALE；'
        'latest provider date = 2026-09-17；policy version = PER_SYMBOL_FAIL_SOFT_PRODUCTION_V1</p></div>'
    )
    before = output.read_text(encoding="utf-8")
    output.write_text(before.replace("</main>", old_block + "</main>", 1), encoding="utf-8", newline="\n")
    before_refresh = output.read_text(encoding="utf-8")

    result = backfill.refresh_existing_volume_enriched_report_coverage(
        output,
        output,
        watchlist,
        original_artifacts={"watchlist_sha256": hashlib.sha256(watchlist.read_bytes()).hexdigest()},
    )
    after = output.read_text(encoding="utf-8")

    new_block = re.search(
        r'<div class="review-callout warning"><strong>数据质量：部分覆盖</strong>.*?</div>',
        after,
        re.S,
    )
    assert new_block is not None
    assert "本次有效评估 3092 只股票，1 只因行情数据异常未参与筛选。下方候选名单不包含这些股票。" in new_block.group(0)
    assert "605366" not in new_block.group(0)
    assert "TARGET_DAY_HISTORICAL_STALE" not in new_block.group(0)
    assert result["evaluated_symbol_count"] == 3092
    assert result["excluded_symbol_count"] == 1
    assert result["candidate_count"] == 10
    assert after.replace(new_block.group(0), "") == before_refresh.replace(old_block, "")


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
