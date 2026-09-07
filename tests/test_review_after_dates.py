import json
from datetime import date, datetime
from pathlib import Path

import review_after
import eod_review
import preopen_review
import track_perf
from test_watchlist_schema import payload


def quote(**overrides):
    value = {
        "code": "600519",
        "name": "贵州茅台",
        "quote_date": "2026-08-27",
        "price": 123.45,
        "prev_close": 120.0,
        "open": 121.0,
        "chg_pct": 2.88,
        "high": 125.0,
        "low": 119.5,
        "turnover": 4.56,
        "vol_ratio": 1.78,
    }
    value.update(overrides)
    return value


def test_explicit_date_is_list_date_only_and_report_keeps_runtime_quote_date(tmp_path, monkeypatch):
    paths_file = tmp_path / "watchlist_20260820.json"
    paths_file.write_text(json.dumps(payload()), encoding="utf-8")
    observed = {}

    def fake_fetch(codes, expected_date):
        observed["codes"] = codes
        observed["expected_date"] = expected_date
        return {"600519": quote()}

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 27, 15, 30)

    monkeypatch.setenv("ASHARE_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(review_after, "datetime", FixedDatetime)
    monkeypatch.setattr(review_after, "fetch_quotes", fake_fetch)

    assert review_after.main(["--mode", "close", "--date", "20260820"]) == 0
    assert observed["codes"] == ["600519"]
    assert observed["expected_date"] == date(2026, 8, 27)

    report = (tmp_path / "reports" / "review_close.md").read_text(encoding="utf-8")
    assert "名单日期 2026-08-20" in report
    assert "行情日期：2026-08-27" in report
    assert "--date 仅选择名单" in report
    assert "MISSING_HISTORICAL_OBSERVATION / UNVERIFIED" in report
    assert "每日轻量状态记录" in report
    assert "持仓" not in report
    assert "配对指标" not in report
    assert "14:45" not in report
    assert "09:25" not in report


def test_review_after_marks_same_day_boundary_order_as_ambiguous():
    candidate = payload()["candidates"][0]
    result = review_after.review_watchlist(
        [candidate],
        {"600519": quote(price=122.0, high=132.0, low=110.0)},
    )

    assert "AMBIGUOUS_SAME_BAR" in result[0]["状态"]
    assert "盘中顺序未知" in result[0]["状态"]


def test_default_review_surfaces_are_isolated_from_out_of_scope_inputs():
    for module in (review_after, eod_review, preopen_review, track_perf):
        source = Path(module.__file__).read_text(encoding="utf-8").lower()
        assert "pairs" not in source
        assert "配对指标" not in source
        assert "持仓体检" not in source
        assert "continuous_speed_probe" not in source
        assert "final_oos" not in source


def test_review_after_help_describes_date_as_list_date_only(capsys):
    try:
        review_after.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    help_text = capsys.readouterr().out
    assert "仅选择名单" in help_text
    assert "不是历史行情 as-of 日期" in help_text


def test_eod_review_is_only_a_compatibility_entrypoint(monkeypatch):
    observed = {}

    def fake_main(argv):
        observed["argv"] = argv
        return 7

    monkeypatch.setattr(eod_review, "_review_after_main", fake_main)

    assert eod_review.main() == 7
    assert observed["argv"] == ["--mode", "close"]
