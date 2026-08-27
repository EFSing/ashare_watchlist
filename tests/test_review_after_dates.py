import json
from datetime import date, datetime

import review_after
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
    (tmp_path / "positions.json").write_text(json.dumps({"positions": []}), encoding="utf-8")
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
    assert "--date 仅表示名单日期" in report


def test_review_after_help_describes_date_as_list_date_only(capsys):
    try:
        review_after.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    help_text = capsys.readouterr().out
    assert "仅选择名单" in help_text
    assert "不是历史行情 as-of 日期" in help_text
