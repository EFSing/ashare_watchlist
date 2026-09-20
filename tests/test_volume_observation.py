from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
import re

import pytest

import b_shadow_monitor as shadow
import render_daily_close_html as renderer
from data_paths import DataPaths
from volume_observation import build_volume_observation_store, write_volume_observation_store
import volume_observation_backfill as backfill
from test_b_phase_volume_path_diagnostic import _fixture


def _bars() -> list[dict[str, float | str]]:
    close, volume, high, low, _dates = _fixture(signal_volume=80.0)
    close[63:69] = [10.0, 10.2, 10.0, 10.1, 10.1, 10.0]
    close[-1] = 10.0
    volume[63:69] = [80.0, 40.0, 20.0, 60.0, 30.0, 10.0]
    start = date(2026, 7, 11)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "open": float(max(low[index], min(high[index], close[index]))),
            "high": float(high[index]),
            "low": float(low[index]),
            "close": float(close[index]),
            "volume": float(volume[index]),
        }
        for index in range(len(close))
    ]


def _candidate(code: str = "002394", score: int = 70) -> dict[str, object]:
    return {
        "code": code,
        "name": f"候选{code}",
        "score": score,
        "price": 10.0,
        "signal_id": f"B_BREAKOUT_RETEST_LEGACY_V1_1:2026-09-18:{code}:B_BREAKOUT_RETEST",
    }


def test_independent_store_uses_stock_klines_without_index_and_renderer_prefers_it(tmp_path):
    candidate = _candidate()
    manifest = {
        "status": "READY_FOR_STRATEGY_EVALUATION",
        "signal_date": "2026-09-18",
        "stock_klines": [{"symbol": "002394", "bars": _bars()}],
    }
    store = build_volume_observation_store([candidate], manifest, "2026-09-18")
    assert store["status"] == "COMPLETE"
    assert store["complete_count"] == 1
    paths = DataPaths(tmp_path / "data")
    path = write_volume_observation_store(paths.volume_observation_file("2026-09-18"), store)
    mapping, status = renderer._load_volume_observations(
        paths,
        "2026-09-18",
        {"candidates": [candidate]},
    )
    assert path.exists()
    assert status == "COMPLETE"
    rows = renderer._watchlist_rows(
        {"candidates": [candidate]},
        {"signals": {}},
        "2026-09-18",
        {"current_signal_context": {}},
        mapping,
    )
    observation = rows[0]["volume_observation"]
    assert observation["down_volume_share"] == pytest.approx(110.0 / 240.0)
    assert observation["up_down_volume_ratio"] == pytest.approx(50.0 / (110.0 / 3.0))


def test_compact_card_has_baseline_direction_and_sample_short_reason():
    text = renderer._volume_observations_html({
        "window_days": None,
        "down_volume_share": 0.548,
        "up_down_volume_ratio": 1.65,
        "pullback_volume_decay_ratio": None,
        "missing_reason": {"pullback_volume_decay_ratio": "PULLBACK_WINDOW_LT_4"},
    })
    assert text.count("volume-metric-row") == 3
    assert "下跌日量占比" in text
    assert "涨/跌日均量比" in text
    assert "后半/前半均量比" in text
    assert "基线 1.00×" in text
    assert "← 缩量" in text and "放量 →" in text
    assert "样本不足" in text
    assert "回踩窗口不足 4 个交易日" in text
    assert "PULLBACK_WINDOW_LT_4" in text
    assert "不参与筛选/排名" in text
    assert "down_volume_share" not in text


def test_enriched_report_maps_by_code_preserves_formal_order_and_scrubs_private_path(tmp_path):
    candidates = [_candidate(code, score=40 + index) for index, code in enumerate(backfill.LOCKED_CODES)]
    watchlist_payload = {"date": "2026-09-18", "mode": "close", "strategy_version": backfill.EXPECTED_STRATEGY, "candidates": candidates}
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps(watchlist_payload, ensure_ascii=False), encoding="utf-8")
    observations = []
    for index, candidate in enumerate(candidates):
        observations.append({
            **candidate,
            "observation": {
                "observation_version": shadow.VOLUME_OBSERVATION_VERSION,
                "protocol_commit_sha": shadow.VOLUME_OBSERVATION_PROTOCOL_COMMIT_SHA,
                "window_days": None,
                "down_volume_share": 0.10 + index / 100,
                "up_down_volume_ratio": 0.80 + index / 100,
                "pullback_volume_decay_ratio": None if candidate["code"] == "600929" else 0.60 + index / 100,
                "missing_reason": {"pullback_volume_decay_ratio": "PULLBACK_WINDOW_LT_4"} if candidate["code"] == "600929" else {},
            },
            "valid": True,
            "complete": candidate["code"] != "600929",
        })
    summary = {
        "candidates": observations,
        "original_artifacts": {
            "watchlist_sha256": hashlib.sha256(watchlist_path.read_bytes()).hexdigest(),
        },
    }
    display_order = ["603096", "001222", "601599", "605003", "600929", "000701", "600689", "603628", "000807", "001217"]
    articles = []
    for rank, code in enumerate(display_order, start=1):
        articles.append(
            f'<article class="watch-row"><div class="security"><strong>{code}</strong><span>候选{code}</span></div>'
            '<div class="volume-observations"><div class="volume-card"><div>old</div></div></div></article>'
        )
    formal = (
        '<!doctype html><html><head><meta name="input-coverage-json" content="C:\\Users\\soush\\private\\input.json">'
        '<title>Formal</title></head><body><main>' + ''.join(articles) + '</main></body></html>'
    )
    formal_path = tmp_path / "formal.html"
    formal_path.write_text(formal, encoding="utf-8")
    output = tmp_path / "daily_close_20260918_volume_enriched.html"
    result = backfill.render_volume_enriched_report(
        formal_path,
        output,
        summary,
        expected_formal_report_sha256=hashlib.sha256(formal.encode("utf-8")).hexdigest(),
    )
    text = output.read_text(encoding="utf-8")
    ranked = re.findall(r'<article class="watch-row".*?<span class="watch-rank">(\d+)</span>.*?<strong>(\d{6})</strong>', text, re.S)
    assert result["candidate_count"] == 10
    assert "RETROSPECTIVE_VOLUME_ENRICHMENT" in text
    assert text.count('class="volume-observations"') == 10
    assert "C:\\Users" not in text
    assert "样本不足" in text
    assert "down_volume_share" not in text
    assert "605003" in text
