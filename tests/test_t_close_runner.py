from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from types import SimpleNamespace

import t_close_runner as runner
from live_acquisition import LiveAcquisitionError
from trading_calendar import TradingCalendar


def test_runner_persists_input_package_before_generating_watchlist(monkeypatch, tmp_path):
    events = []
    package = SimpleNamespace(
        generation_input_manifest=SimpleNamespace(signal_date="2026-08-27"),
        display_names={"600519": "测试股份"},
        market_env={"as_of_date": "2026-08-27"},
        provenance={
            "evidence_capture": {"status": "T_CLOSE_VOLATILE_EVIDENCE_SECURED"},
            "candidate": {
                "strategy_version": runner.B_STRATEGY_BINDING.strategy_version,
                "spec_sha256": runner.B_STRATEGY_BINDING.strategy_spec_sha256,
            },
        },
    )
    persisted = SimpleNamespace(
        status="PERSISTED",
        path=tmp_path / "input.json",
        file_sha256="a" * 64,
    )
    candidate = SimpleNamespace(
        status=runner.RUN_SUCCESS,
        output_path=tmp_path / "watchlist.json",
        output_sha256="b" * 64,
        candidate_count=1,
        run_manifest_path=tmp_path / "run_manifest.json",
    )

    def fake_acquire(*args, **kwargs):
        events.append("acquire")
        assert kwargs["evidence_root"] == tmp_path / "evidence"
        return package

    def fake_persist(value, output_root):
        events.append("persist_package")
        assert value is package
        assert output_root == tmp_path
        return persisted

    class FakeStore:
        def __init__(self, output_root):
            assert output_root == tmp_path

        def generate(self, manifest, *, names, market_env, strategy_binding, input_provenance):
            events.append("generate_watchlist")
            assert manifest is package.generation_input_manifest
            assert names == package.display_names
            assert market_env == package.market_env
            assert strategy_binding is runner.B_STRATEGY_BINDING
            assert input_provenance is package.provenance
            assert events == ["acquire", "persist_package", "generate_watchlist"]
            return candidate

    monkeypatch.setattr(runner, "acquire_live_generation_inputs", fake_acquire)
    monkeypatch.setattr(runner, "persist_live_input_package", fake_persist)
    monkeypatch.setattr(runner, "DevelopmentCandidateStore", FakeStore)
    monkeypatch.setattr(runner, "_git_sha", lambda: "c" * 40)

    result = runner.run("2026-08-27", tmp_path, tmp_path / "evidence")

    assert result["status"] == "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED"
    assert result["input_package"]["path"] == str(persisted.path)
    assert result["watchlist"]["path"] == str(candidate.output_path)
    assert events == ["acquire", "persist_package", "generate_watchlist"]


def test_main_persists_daily_close_bundle_after_successful_tclose_run(monkeypatch, tmp_path, capsys):
    watchlist_path = tmp_path / "watchlist_20260910.json"
    watchlist_path.write_text("{}", encoding="utf-8")
    bundle = {"status": "READY", "dated_html": "daily_close_20260910.html"}

    monkeypatch.setattr(
        runner,
        "run",
        lambda as_of_date, data_root, evidence_root, now_bjt=None, **kwargs: {
            "status": runner.T_CLOSE_SUCCESS_STATUS,
            "watchlist": {"path": str(watchlist_path)},
        },
    )
    monkeypatch.setattr(runner, "_run_daily_close_reporting", lambda as_of_date, data_root: bundle)

    assert runner.main([
        "--as-of-date", "2026-09-10",
        "--data-root", str(tmp_path / "data"),
        "--evidence-root", str(tmp_path / "evidence"),
    ]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == runner.T_CLOSE_SUCCESS_STATUS
    assert result["daily_close_bundle"] == bundle


def test_main_emits_structured_live_acquisition_diagnostics(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        runner,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            LiveAcquisitionError(
                "INPUT_DATE_MISMATCH",
                "stale target-day historical bar",
                {
                    "symbol": "600519",
                    "target_date": "2026-09-17",
                    "latest_historical_date": "2026-09-16",
                    "provider": "HiThink Financial-API",
                    "retry_count": 1,
                },
            )
        ),
    )

    assert runner.main([
        "--as-of-date", "2026-09-17",
        "--data-root", str(tmp_path / "data"),
        "--evidence-root", str(tmp_path / "evidence"),
    ]) == 1
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "T_CLOSE_RUN_FAILED"
    assert result["error_status"] == "INPUT_DATE_MISMATCH"
    assert result["diagnostics"]["symbol"] == "600519"
    assert result["diagnostics"]["retry_count"] == 1


def test_preflight_marks_authorized_weekend_backfill_without_provider_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("HITHINK_FINANCE_API_KEY", "test-only-key")
    monkeypatch.setattr(
        runner,
        "default_calendar",
        lambda: TradingCalendar(holidays=set(), session_close_time=time(15, 0)),
    )

    result = runner._preflight(
        "2026-09-11",
        tmp_path / "data",
        tmp_path / "evidence",
        allow_weekend_backfill=True,
        now_bjt=datetime(2026, 9, 12, 15, 5, tzinfo=timezone.utc).astimezone(runner._BJT),
    )

    assert result["status"] == "AUTHORIZED_WEEKEND_BACKFILL_READY"
    assert result["acquisition_timing"] == runner.AUTHORIZED_WEEKEND_BACKFILL
    assert result["target_session"] == "2026-09-11"
    assert result["actual_acquisition_date"] == "2026-09-12"
    assert result["authorization"] == "explicit user-authorized weekend backfill"
    assert result["provider_calls"] == "NOT_RUN_BEFORE_T_CLOSE"


def test_preflight_cleanly_skips_non_xshg_session_without_provider_calls(monkeypatch, tmp_path):
    monkeypatch.delenv("HITHINK_FINANCE_API_KEY", raising=False)
    monkeypatch.setattr(
        runner,
        "default_calendar",
        lambda: TradingCalendar(holidays={date(2026, 9, 14)}, session_close_time=time(15, 0)),
    )

    result = runner._preflight(
        "2026-09-14",
        tmp_path / "data",
        tmp_path / "evidence",
        now_bjt=datetime(2026, 9, 14, 18, 17, tzinfo=runner._BJT),
    )

    assert result["status"] == "SKIPPED_NON_TRADING_DAY"
    assert result["xshg_session"] == "NO"
    assert result["provider_calls"] == "NOT_RUN"
    assert result["credential_context"] == "MISSING_HITHINK_FINANCE_API_KEY"


def test_preflight_fails_safe_when_calendar_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("HITHINK_FINANCE_API_KEY", "test-only-key")
    monkeypatch.setattr(runner, "default_calendar", lambda: TradingCalendar())

    result = runner._preflight(
        "2026-09-14",
        tmp_path / "data",
        tmp_path / "evidence",
        now_bjt=datetime(2026, 9, 14, 18, 17, tzinfo=runner._BJT),
    )

    assert result["status"] == "CALENDAR_UNAVAILABLE"
    assert result["provider_calls"] == "NOT_RUN"


def test_preflight_reports_missing_credential_on_a_trading_session(monkeypatch, tmp_path):
    monkeypatch.delenv("HITHINK_FINANCE_API_KEY", raising=False)
    monkeypatch.setattr(
        runner,
        "default_calendar",
        lambda: TradingCalendar(holidays=set(), session_close_time=time(15, 0)),
    )

    result = runner._preflight(
        "2026-09-14",
        tmp_path / "data",
        tmp_path / "evidence",
        now_bjt=datetime(2026, 9, 14, 18, 17, tzinfo=runner._BJT),
    )

    assert result["status"] == "SCHEDULED_TASK_CREDENTIAL_CONTEXT_NOT_READY"
    assert result["credential_context"] == "MISSING_HITHINK_FINANCE_API_KEY"
    assert result["provider_calls"] == "NOT_RUN_BEFORE_T_CLOSE"
