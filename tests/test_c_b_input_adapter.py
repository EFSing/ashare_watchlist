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
    receipt, manifest_sha = _handoff(path, sha, kwargs.pop("target_date", T))
    return adapter.consume_b_input(path, target_date=T, expected_sha256=sha,
                                   handoff_receipt_path=receipt,
                                   expected_handoff_manifest_sha256=manifest_sha,
                                   read_at=datetime(2026, 9, 22, 19, tzinfo=BJT), **kwargs)


def _handoff(path: Path, sha: str, day: str) -> tuple[Path, str]:
    manifest = {
        "schema_version": "B_C_READONLY_HANDOFF_V1", "status": "EXPORTED_LOCAL_UNVERIFIED_REMOTE",
        "target_date": day, "package_sha256": sha,
        "exported_at_bjt": f"{day}T17:30:00+08:00",
        "generation_fingerprint": json.loads(path.read_bytes()).get("generation_fingerprint") if path.is_file() else None,
        "files": [{"path": "package.json", "sha256": sha, "bytes": path.stat().st_size}] if path.is_file() else [],
    }
    manifest_path = path.parent / "handoff.json"
    manifest_path.write_bytes(adapter._canonical(manifest))
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    receipt = {
        "schema_version": "B_C_HANDOFF_RECEIPT_V1", "status": "HANDOFF_VERIFIED",
        "local_export": "SUCCESS", "private_persistence": "READBACK_VERIFIED",
        "independent_download": "SUCCESS", "per_file_sha_and_bytes": "VERIFIED",
        "target_date": day, "package_sha256": sha,
        "handoff_manifest_sha256": manifest_sha,
        "generation_fingerprint": manifest["generation_fingerprint"],
        "files": manifest["files"], "repository": "private/test", "tag": "test",
        "asset": "test.zip", "archive_sha256": "a" * 64,
        "exported_at_bjt": f"{day}T17:30:00+08:00",
        "download_verified_at_bjt": f"{day}T18:00:00+08:00",
    }
    receipt_path = path.parent / "handoff-receipt.json"
    receipt_path.write_bytes(adapter._canonical(receipt))
    return receipt_path, manifest_sha


def test_full_b_package_preserves_st_gap_without_c_signal(c_root: Path, tmp_path: Path) -> None:
    path, sha = _package(tmp_path)
    original = path.read_bytes()
    result = _consume(path, sha)
    assert result["status"] == capture.C_PARTIAL_UNVERIFIED
    assert result["observation_count"] == 0
    record = json.loads((c_root / result["record"]).read_text(encoding="utf-8"))
    assert record["price_protocol"] == adapter.PRICE_PROTOCOL
    assert record["source"]["b_package_actual_sha256"] == sha
    assert "B_T_DAY_ST_SOURCE_UNVERIFIED:600000" in result["gaps"]
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
    handoff_package = tmp_path / "handoff" / "package.json"
    handoff_package.parent.mkdir()
    handoff_package.write_bytes(original)
    receipt, manifest_sha = _handoff(handoff_package, persisted.file_sha256, "2026-08-27")
    result = adapter.consume_b_input(
        handoff_package, target_date="2026-08-27", expected_sha256=persisted.file_sha256,
        handoff_receipt_path=receipt, expected_handoff_manifest_sha256=manifest_sha,
        read_at=datetime(2026, 8, 27, 19, tzinfo=BJT),
    )
    assert result["status"] == capture.C_PARTIAL_UNVERIFIED
    assert result["observation_count"] == 0
    record = json.loads((c_root / result["record"]).read_bytes())
    assert record["source"]["b_input_coverage"]["excluded_symbols"][0]["symbol"] == "605366"
    assert record["source"]["coverage_groups"]["b_evaluated_symbols"] == ["600519"]
    assert record["source"]["coverage_groups"]["c_st_evidence_unresolved"] == ["600519"]
    assert "B_INPUT_FAILURE_ISOLATED_SYMBOLS_MISSING_FROM_C_HISTORY" in result["gaps"]
    assert persisted.path.read_bytes() == original
    altered = json.loads(original)
    altered["generation_input_manifest"]["input_fingerprint"] = "0" * 64
    altered.pop("content_sha256")
    altered["content_sha256"] = hashlib.sha256(adapter._canonical(altered)).hexdigest()
    altered_path = tmp_path / "altered.json"
    altered_path.write_bytes(adapter._canonical(altered))
    altered_sha = hashlib.sha256(altered_path.read_bytes()).hexdigest()
    altered_handoff = tmp_path / "altered-handoff" / "package.json"
    altered_handoff.parent.mkdir()
    altered_handoff.write_bytes(altered_path.read_bytes())
    altered_receipt, altered_manifest_sha = _handoff(altered_handoff, altered_sha, "2026-08-27")
    rejected = adapter.consume_b_input(altered_handoff, target_date="2026-08-27",
                                       expected_sha256=altered_sha,
                                       handoff_receipt_path=altered_receipt,
                                       expected_handoff_manifest_sha256=altered_manifest_sha,
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
    handoff_package = tmp_path / "handoff" / "package.json"
    handoff_package.parent.mkdir()
    handoff_package.write_bytes(persisted.path.read_bytes())
    receipt, manifest_sha = _handoff(handoff_package, persisted.file_sha256, "2026-08-27")
    result = adapter.consume_b_input(handoff_package, target_date="2026-08-27",
                                     expected_sha256=persisted.file_sha256,
                                     handoff_receipt_path=receipt, expected_handoff_manifest_sha256=manifest_sha,
                                     evidence_root=evidence_root,
                                     read_at=datetime(2026, 8, 27, 19, tzinfo=BJT))
    assert result["observation_count"] == 0
    assert "B_RAW_SOURCE_SHA_UNVERIFIED" not in result["gaps"]
    capture = package.provenance["evidence_capture"]["captures"][0]
    raw_path = evidence_root / "20260827" / capture["component"] / (
        hashlib.sha256(capture["logical_component_identity"].encode()).hexdigest() + ".raw")
    raw_path.write_bytes(b"corrupted")
    corrupt = adapter.consume_b_input(handoff_package, target_date="2026-08-27",
                                      expected_sha256=persisted.file_sha256,
                                      handoff_receipt_path=receipt, expected_handoff_manifest_sha256=manifest_sha,
                                      evidence_root=evidence_root,
                                      read_at=datetime(2026, 8, 27, 19, 1, tzinfo=BJT))
    assert "B_RAW_SOURCE_SHA_UNVERIFIED" in corrupt["gaps"]


def test_exact_handoff_identity_and_nine_isolated_symbols(c_root: Path, tmp_path: Path) -> None:
    path, _ = _package(tmp_path)
    package = json.loads(path.read_bytes())
    excluded = [{"symbol": f"600{i:03d}", "reason": "TARGET_DAY_HISTORICAL_STALE"}
                for i in range(1, 10)]
    coverage = package["provenance"]["input_coverage"]
    coverage.update({"excluded_symbol_count": 9, "excluded_symbols": excluded})
    package["generation_input_manifest"]["provider_version_metadata"]["input_coverage"] = coverage
    package.pop("content_sha256")
    package["content_sha256"] = hashlib.sha256(adapter._canonical(package)).hexdigest()
    path.write_bytes(adapter._canonical(package))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    result = _consume(path, sha)
    assert result["status"] == capture.C_PARTIAL_UNVERIFIED
    record = json.loads((c_root / result["record"]).read_bytes())
    assert len(record["source"]["coverage_groups"]["b_input_isolated"]) == 9
    assert record["source"]["coverage_groups"]["b_evaluated_symbols"] == ["600000"]
    assert record["observations"] == []
    receipt = path.parent / "handoff-receipt.json"
    receipt_data = json.loads(receipt.read_bytes())
    receipt_data["status"] = "EXPORTED_LOCAL_UNVERIFIED_REMOTE"
    receipt.write_bytes(adapter._canonical(receipt_data))
    failed = adapter.consume_b_input(path, target_date=T, expected_sha256=sha,
                                     handoff_receipt_path=receipt,
                                     expected_handoff_manifest_sha256=record["source"]["handoff"]["manifest_sha256"],
                                     read_at=datetime(2026, 9, 22, 19, tzinfo=BJT))
    assert "B_HANDOFF_IDENTITY_MISMATCH" in failed["gaps"]


def test_missing_b_volume_does_not_create_c_observation(c_root: Path, tmp_path: Path) -> None:
    path, _ = _package(tmp_path)
    package = json.loads(path.read_bytes())
    package["generation_input_manifest"]["stock_klines"][0]["bars"][-1].pop("volume")
    package.pop("content_sha256")
    package["content_sha256"] = hashlib.sha256(adapter._canonical(package)).hexdigest()
    path.write_bytes(adapter._canonical(package))
    result = _consume(path, hashlib.sha256(path.read_bytes()).hexdigest())
    assert result["observation_count"] == 0
    assert result["status"] == capture.C_CAPTURE_FAILED


def test_st_name_and_late_handoff_remain_outside_c_observation(c_root: Path, tmp_path: Path) -> None:
    path, _ = _package(tmp_path)
    package = json.loads(path.read_bytes())
    package["display_names"]["600000"] = "*ST浦发"
    package.pop("content_sha256")
    package["content_sha256"] = hashlib.sha256(adapter._canonical(package)).hexdigest()
    path.write_bytes(adapter._canonical(package))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    result = _consume(path, sha)
    record = json.loads((c_root / result["record"]).read_bytes())
    assert record["observations"] == []
    assert record["source"]["coverage_groups"]["c_rule_or_st_excluded"] == [
        {"symbol": "600000", "reason": "ST_NAME_PREFIX; T_DAY_TIME_UNVERIFIED"}]
    receipt = path.parent / "handoff-receipt.json"
    value = json.loads(receipt.read_bytes())
    value["download_verified_at_bjt"] = "2026-09-23T18:00:00+08:00"
    receipt.write_bytes(adapter._canonical(value))
    late = adapter.consume_b_input(path, target_date=T, expected_sha256=sha,
                                   handoff_receipt_path=receipt,
                                   expected_handoff_manifest_sha256=record["source"]["handoff"]["manifest_sha256"],
                                   read_at=datetime(2026, 9, 23, 19, tzinfo=BJT))
    assert "B_HISTORICAL_HANDOFF" in late["gaps"]


def _timed_source(path: Path, evidence_root: Path, *, isolated: int = 0,
                  received: str = "2026-09-22T17:20:00+08:00") -> str:
    package = json.loads(path.read_bytes())
    symbol = "600000"
    captures = []
    for source, logical, body in (
        ("/api/meta/tickers/list", "ticker-page",
         {"code": 0, "data": {"item": [{"ticker": symbol, "name": package["display_names"][symbol]}]}}),
        ("/api/a-share/prices/historical", f"thscode={symbol}.SH",
         {"code": 0, "data": {"item": []}}),
    ):
        payload = adapter._canonical(body)
        digest = hashlib.sha256(payload).hexdigest()
        base = evidence_root / "20260922" / "hithink_response" / hashlib.sha256(logical.encode()).hexdigest()
        base.parent.mkdir(parents=True, exist_ok=True)
        base.with_suffix(".raw").write_bytes(payload)
        metadata = {"file_sha256": digest, "byte_length": len(payload),
                    "logical_component_identity": logical, "source_identity": source,
                    "request_identity": logical,
                    "requested_at_bjt": "2026-09-22T17:19:00+08:00",
                    "received_at_bjt": received}
        base.with_suffix(".json").write_bytes(adapter._canonical(metadata))
        captures.append({"component": "hithink_response", "logical_component_identity": logical,
                         "source_identity": source, "file_sha256": digest,
                         "completeness_status": "COMPLETE"})
    package["provenance"]["evidence_capture"] = {"captures": captures}
    coverage = package["provenance"]["input_coverage"]
    coverage["excluded_symbols"] = [{"symbol": f"600{i:03d}",
                                      "reason": "TARGET_DAY_HISTORICAL_STALE"}
                                     for i in range(1, isolated + 1)]
    coverage["excluded_symbol_count"] = isolated
    package["generation_input_manifest"]["provider_version_metadata"]["input_coverage"] = coverage
    quality = package["generation_input_manifest"]["provider_version_metadata"]["universe_quality"]
    quality["retained_count"] = isolated + 1
    package.pop("content_sha256")
    package["content_sha256"] = hashlib.sha256(adapter._canonical(package)).hexdigest()
    path.write_bytes(adapter._canonical(package))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("isolated", [0, 9])
def test_timed_price_observation_keeps_volume_and_market_coverage_separate(
    c_root: Path, tmp_path: Path, isolated: int,
) -> None:
    path, _ = _package(tmp_path)
    evidence_root = tmp_path / "raw"
    sha = _timed_source(path, evidence_root, isolated=isolated)
    result = _consume(path, sha, evidence_root=evidence_root)
    assert result["status"] == adapter.PRICE_OBSERVATION_VOLUME_UNVERIFIED
    assert result["observation_count"] == 1
    record = json.loads((c_root / result["record"]).read_bytes())
    assert record["source"]["coverage_status"] == ("COMPLETE" if isolated == 0 else "PARTIAL_UNVERIFIED")
    assert len(record["source"]["coverage_groups"]["b_input_isolated"]) == isolated
    for rule in ("BALANCED_A", "CONSERVATIVE_B"):
        observation = record["observations"][0]["rules"][rule]
        volume = observation["volume_observation"]
        assert volume["feature_status"] == "VOLUME_FEATURE_COMPUTED"
        assert volume["status"] == "VOLUME_BASIS_UNVERIFIED"
        assert volume["t_day_relative_volume"]["relative_volume_ratio"] == 1.0
        assert volume["pullback_path"]["status"] == "PRICE_STRUCTURE_UNAVAILABLE"
        assert volume["raw_t_day_volume"] == 100.0
        assert volume["forward_adjustment_effect"] == "UNRESOLVED"
        assert volume["volume_confirmation_valid"] is False
        assert observation["entry_candidate"] is False
        assert observation["event_identity"] is None
    assert record["prospective_captured"] is False


def test_same_runner_reads_exact_frozen_bytes_without_private_handoff(c_root: Path, tmp_path: Path) -> None:
    path, _ = _package(tmp_path)
    evidence_root = tmp_path / "raw"
    sha = _timed_source(path, evidence_root)
    before = path.read_bytes()
    result = adapter.consume_b_input(
        path, target_date=T, expected_sha256=sha, local_runner_input=True,
        evidence_root=evidence_root, read_at=datetime(2026, 9, 22, 19, tzinfo=BJT),
    )
    assert result["status"] == adapter.PRICE_OBSERVATION_VOLUME_UNVERIFIED
    record = json.loads((c_root / result["record"]).read_bytes())
    assert record["source"]["handoff"]["mode"] == "SAME_RUNNER_READ_ONLY"
    assert record["source"]["handoff"]["private_persistence"] == "NOT_CLAIMED"
    assert path.read_bytes() == before
    next_day = adapter.consume_b_input(
        path, target_date=T, expected_sha256=sha, local_runner_input=True,
        evidence_root=evidence_root, read_at=datetime(2026, 9, 23, 9, tzinfo=BJT),
    )
    assert next_day["status"] == capture.C_CAPTURE_FAILED
    assert "B_HISTORICAL_LOCAL_RUNNER_INPUT" in next_day["gaps"]


def test_price_event_keeps_pullback_volume_without_formal_candidate() -> None:
    from test_c_pre_outcome_design import _synthetic_entry_bars

    bars = _synthetic_entry_bars()
    observation = adapter._price_only_observation("600000", bars[-1]["date"], bars, "BALANCED_A")
    volume = observation["volume_observation"]
    assert observation["price_structure_match"] is True
    assert observation["price_structure_event_identity"]
    assert observation["entry_candidate"] is False
    assert observation["event_identity"] is None
    assert volume["feature_status"] == "VOLUME_FEATURE_COMPUTED"
    assert volume["t_day_relative_volume"]["relative_volume_ratio"] is not None
    assert volume["pullback_path"]["pullback_to_reference_median_ratio"] is not None
    assert volume["pullback_path"]["second_to_first_half_median_ratio"] is not None
    assert "up_to_down_volume_median_ratio" in volume["pullback_path"]
    assert volume["volume_confirmation_valid"] is False


def test_runner_start_cannot_replace_response_receive_time(c_root: Path, tmp_path: Path) -> None:
    path, _ = _package(tmp_path)
    evidence_root = tmp_path / "raw"
    sha = _timed_source(path, evidence_root, received="2026-09-23T17:20:00+08:00")
    result = _consume(path, sha, evidence_root=evidence_root)
    assert result["observation_count"] == 0
    assert "B_PROVIDER_REQUEST_TIME_UNVERIFIED" in result["gaps"]
