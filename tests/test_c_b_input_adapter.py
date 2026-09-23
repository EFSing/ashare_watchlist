from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

import c_b_input_adapter as adapter
import c_prospective_capture as capture
from c_state_store import sync_c_store

T = "2026-09-22"
BJT = timezone(timedelta(hours=8))


@pytest.fixture
def c_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data/research/c_prospective_capture_v1"
    monkeypatch.setattr(capture, "C_OUTPUT_ROOT", root)
    return root


def _package(tmp_path: Path, *, include_history: bool = True, day: str = T) -> tuple[Path, str]:
    dates = []
    current = date.fromisoformat(day)
    while len(dates) < 110:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current -= timedelta(days=1)
    bars = [{"date": d, "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 100.0}
            for d in reversed(dates)]
    symbol = "600000"
    kline = {"symbol": symbol, "as_of_date": day, "provider": "HiThink Financial-API",
             "adjustment_mode": "PROVIDER_QFQ_SNAPSHOT", "bars": bars,
             "normalized_data_sha256": adapter._b_kline_sha({"symbol": symbol, "bars": bars})}
    coverage = {"evaluated_symbol_count": 1, "excluded_symbol_count": 0, "excluded_symbols": []}
    manifest = {"status": "READY_FOR_STRATEGY_EVALUATION", "signal_date": day,
                "input_fingerprint": "fingerprint", "universe": {"symbols": [symbol]},
                "quote_snapshot": {"quotes": {symbol: {"quote_date": day}}},
                "stock_klines": [kline] if include_history else [],
                "provider_version_metadata": {"universe_quality": {"source_row_count": 5576}, "input_coverage": coverage}}
    package = {"schema_version": adapter.PACKAGE_SCHEMA, "generation_input_manifest": manifest,
               "market_env": {"as_of_date": day}, "display_names": {symbol: "浦发银行"},
               "generation_fingerprint": "generation", "provenance": {"retrieved_at_bjt": f"{day}T17:17:00+08:00", "input_coverage": coverage}}
    package["content_sha256"] = hashlib.sha256(adapter._canonical(package)).hexdigest()
    path = tmp_path / "package.json"
    path.write_bytes(adapter._canonical(package))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _consume(path: Path, sha: str, **kwargs):
    return adapter.consume_b_input(path, target_date=T, expected_sha256=sha,
                                   read_at=datetime(2026, 9, 22, 19, tzinfo=BJT), **kwargs)


def test_full_b_package_creates_independent_partial_observations(c_root: Path, tmp_path: Path) -> None:
    path, sha = _package(tmp_path)
    original = path.read_bytes()
    result = _consume(path, sha)
    assert result["status"] == capture.C_PARTIAL_UNVERIFIED
    assert result["observation_count"] == 1
    record = json.loads((c_root / result["record"]).read_text(encoding="utf-8"))
    assert set(record["observations"][0]["rules"]) == set(capture.RULE_CANDIDATES)
    assert record["source"]["b_package_actual_sha256"] == sha
    assert "B_FORWARD_ADJUSTED_PRICE_INCOMPATIBLE_WITH_C_UNADJUSTED_BASIS" in result["gaps"]
    assert not record["prospective_captured"]
    assert path.read_bytes() == original


@pytest.mark.parametrize("kind,expected", [
    ("candidate_only", "B_FULL_INPUT_MISSING"),
    ("no_history", "B_FULL_INPUT_MISSING"),
    ("bad_sha", "B_PACKAGE_SHA_MISMATCH"),
    ("wrong_day", "B_TARGET_DATE_MISMATCH"),
    ("late_backfill", "B_HISTORICAL_OR_PRE_CLOSE_INPUT"),
    ("missing", "B_INPUT_READ_OR_SCHEMA_FAILED:FileNotFoundError"),
])
def test_incomplete_or_invalid_b_source_fails_closed(c_root: Path, tmp_path: Path, kind: str, expected: str) -> None:
    path, sha = _package(tmp_path, include_history=kind != "no_history", day="2026-09-21" if kind == "wrong_day" else T)
    if kind == "candidate_only":
        path.write_text('{"candidate_count": 1}', encoding="utf-8")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
    elif kind == "bad_sha":
        sha = "0" * 64
    elif kind == "late_backfill":
        value = json.loads(path.read_text(encoding="utf-8"))
        value["provenance"]["retrieved_at_bjt"] = "2026-09-23T17:17:00+08:00"
        value.pop("content_sha256")
        value["content_sha256"] = hashlib.sha256(adapter._canonical(value)).hexdigest()
        path.write_bytes(adapter._canonical(value))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
    elif kind == "missing":
        path = tmp_path / "not-persisted.json"
    result = _consume(path, sha)
    assert result["status"] == capture.C_CAPTURE_FAILED
    assert expected in result["gaps"]
    assert (c_root / result["record"]).is_file()


def test_failure_evidence_publishes_to_private_c_state(c_root: Path, tmp_path: Path) -> None:
    result = _consume(tmp_path / "b-not-ready.json", "0" * 64)
    state_repo = tmp_path / "private-c-state"
    assert sync_c_store(state_repo, direction="publish") == 1
    restored = state_repo / "data/research/c_prospective_capture_v1" / result["record"]
    assert restored.is_file()
    assert json.loads(restored.read_text(encoding="utf-8"))["status"] == capture.C_CAPTURE_FAILED


def test_b_retry_then_ready_without_provider_or_b_write(c_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("C made a provider request"))
    missing = tmp_path / "not-ready.json"
    first = _consume(missing, "0" * 64)
    assert first["status"] == capture.C_CAPTURE_FAILED
    path, sha = _package(tmp_path)
    before = path.read_bytes()
    second = _consume(path, sha)
    assert second["status"] == capture.C_PARTIAL_UNVERIFIED
    assert path.read_bytes() == before
    assert first["record"] != second["record"]


def test_real_b_serialization_and_isolated_coverage_are_consumed(c_root: Path, tmp_path: Path) -> None:
    from test_live_acquisition import _bars, _multi_symbol_acquire

    package = _multi_symbol_acquire(bars_by_code={
        "605366": _bars(last_date="2026-08-26", count=141),
        "600519": _bars(last_date="2026-08-27", count=141),
    })
    persisted = __import__("live_acquisition").persist_live_input_package(package, tmp_path)
    original = persisted.path.read_bytes()
    result = adapter.consume_b_input(
        persisted.path, target_date="2026-08-27", expected_sha256=persisted.file_sha256,
        read_at=datetime(2026, 8, 27, 19, tzinfo=BJT),
    )
    assert result["status"] == capture.C_PARTIAL_UNVERIFIED
    assert result["observation_count"] == 1
    record = json.loads((c_root / result["record"]).read_bytes())
    assert record["source"]["b_input_coverage"]["excluded_symbols"][0]["symbol"] == "605366"
    assert record["observations"][0]["symbol"] == "600519"
    assert "B_INPUT_FAILURE_ISOLATED_SYMBOLS_MISSING_FROM_C_HISTORY" in result["gaps"]
    assert persisted.path.read_bytes() == original
    altered = json.loads(original)
    altered["generation_input_manifest"]["input_fingerprint"] = "0" * 64
    altered.pop("content_sha256")
    altered["content_sha256"] = hashlib.sha256(adapter._canonical(altered)).hexdigest()
    altered_path = tmp_path / "altered.json"
    altered_path.write_bytes(adapter._canonical(altered))
    rejected = adapter.consume_b_input(altered_path, target_date="2026-08-27",
                                       expected_sha256=hashlib.sha256(altered_path.read_bytes()).hexdigest(),
                                       read_at=datetime(2026, 8, 27, 19, tzinfo=BJT))
    assert "B_GENERATION_IDENTITY_MISMATCH" in rejected["gaps"]


def test_real_b_evidence_sidecars_are_sha_verified(c_root: Path, tmp_path: Path) -> None:
    import live_acquisition as live
    from test_live_acquisition import FakeHiThink, _acquire, _bars

    evidence_root = tmp_path / "evidence"
    package = _acquire(evidence_root=evidence_root,
                       hithink_client=FakeHiThink(bars=_bars(count=120), index_bars=_bars(count=120)),
                       stock_bar_count=120)
    persisted = live.persist_live_input_package(package, tmp_path)
    result = adapter.consume_b_input(persisted.path, target_date="2026-08-27",
                                     expected_sha256=persisted.file_sha256, evidence_root=evidence_root,
                                     read_at=datetime(2026, 8, 27, 19, tzinfo=BJT))
    assert result["observation_count"] == 1
    assert "B_RAW_SOURCE_SHA_UNVERIFIED" not in result["gaps"]
    capture = package.provenance["evidence_capture"]["captures"][0]
    raw_path = evidence_root / "20260827" / capture["component"] / (
        hashlib.sha256(capture["logical_component_identity"].encode()).hexdigest() + ".raw")
    raw_path.write_bytes(b"corrupted")
    corrupt = adapter.consume_b_input(persisted.path, target_date="2026-08-27",
                                      expected_sha256=persisted.file_sha256, evidence_root=evidence_root,
                                      read_at=datetime(2026, 8, 27, 19, 1, tzinfo=BJT))
    assert "B_RAW_SOURCE_SHA_UNVERIFIED" in corrupt["gaps"]
