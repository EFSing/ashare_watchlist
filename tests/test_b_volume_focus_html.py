from __future__ import annotations

import json

from b_volume_confirm_focus import ensure_volume_focus_epoch
import render_daily_close_html as renderer
from test_daily_close_html import CALENDAR, _candidate, _paths, _write_tracker, _write_watchlist


def focus_candidate(code: str, name: str, score: int, vol_ratio: float) -> dict[str, object]:
    item = _candidate(code, name, score)
    item.update({
        "vol_ratio": vol_ratio,
        "stop_dist": 4.5,
        "chg": 2.1,
        "target_type": "PRESSURE",
    })
    return item


def test_report_shows_focus_without_changing_canonical_rows(tmp_path):
    _write_watchlist(tmp_path, "20260909", [focus_candidate("002394", "联发股份", 65, 1.1)])
    candidates = [
        focus_candidate("600018", "普通信号", 31, 0.8),
        focus_candidate("002394", "联发股份", 70, 1.57629),
        focus_candidate("600278", "另一信号", 68, 1.1999),
    ]
    watchlist = _write_watchlist(tmp_path, "20260910", candidates)
    before = (tmp_path / "data" / "watchlist_20260910.json").read_bytes()
    tracker = _write_tracker(tmp_path, watchlist)
    ensure_volume_focus_epoch(tracker, "20260910", source_commit="test")
    (tmp_path / "data" / "perf_tracker.json").write_text(json.dumps(tracker), encoding="utf-8")

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    text = renderer.render_html(model)

    assert len(model.watchlist_rows) == 3
    assert [row["code"] for row in model.watchlist_rows] == ["002394", "600278", "600018"]
    assert model.volume_focus["canonical_candidate_count"] == 3
    assert model.volume_focus["focus_candidate_count"] == 1
    assert model.volume_focus["focus_candidates"][0]["code"] == "002394"
    for marker in (
        "实验重点观察", "Volume Confirmation Focus", "OBSERVATIONAL_ONLY", "NOT_FORMAL_B",
        "canonical B candidates", "focus candidates", "focus ratio", "EVIDENCE_ACCUMULATING",
        "canonical Score", "vol_ratio", "RECENT_REPEAT",
    ):
        assert marker in text
    assert text.count('class="focus-card"') == 1
    assert (tmp_path / "data" / "watchlist_20260910.json").read_bytes() == before


def test_focus_empty_state_is_explicit_and_canonical_count_remains_visible(tmp_path):
    watchlist = _write_watchlist(tmp_path, "20260910", [
        focus_candidate("600018", "无量能信号", 60, 1.1999),
        focus_candidate("600019", "缺失量能", 55, 0.0),
    ])
    _write_tracker(tmp_path, watchlist)

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    text = renderer.render_html(model)

    assert model.volume_focus["canonical_candidate_count"] == 2
    assert model.volume_focus["focus_candidate_count"] == 0
    assert "今日无量能确认候选" in text
    assert "canonical B candidates" in text
    assert 'class="focus-card"' not in text


def test_multiple_focus_candidates_use_cards_and_mobile_layout_has_no_page_scroll(tmp_path):
    watchlist = _write_watchlist(tmp_path, "20260910", [
        focus_candidate("600018", "重点一", 60, 1.20),
        focus_candidate("600019", "重点二", 55, 1.21),
        focus_candidate("600020", "普通", 50, 0.5),
    ])
    _write_tracker(tmp_path, watchlist)

    model = renderer.build_report_model("20260910", paths=_paths(tmp_path), calendar=CALENDAR)
    text = renderer.render_html(model)

    assert model.volume_focus["focus_candidate_count"] == 2
    assert text.count('class="focus-card"') == 2
    assert "html { max-width: 100%; overflow-x: hidden" in text
    assert "body { max-width: 100%; margin: 0; overflow-x: hidden" in text
    assert ".focus-candidates { grid-template-columns: 1fr; }" in text
    assert ".focus-card-facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in text
