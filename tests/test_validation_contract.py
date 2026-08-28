import copy
import json

import pytest

from generation_contract import POINT_IN_TIME, PROVIDER_QFQ_SNAPSHOT, next_execution_date
from validation_contract import (
    CURRENT_DATA_BACKFILL,
    FINAL_OOS_FORBIDDEN,
    FUTURE_DATA_INPUT,
    HISTORICAL_ADJUSTED_AS_OF,
    INPUT_DATE_MISMATCH,
    LEGACY_STRATEGY_SPEC_SHA256,
    LEGACY_STRATEGY_VERSION,
    INVALID_SECTOR_EVIDENCE,
    MANIFEST_PROTOCOL_VERSION_INVALID,
    MANIFEST_HASH_MISMATCH,
    MANIFEST_SCHEMA_VERSION_INVALID,
    MISSING_POINT_IN_TIME_EVIDENCE,
    PROTOCOL_SEMANTIC_SHA256,
    REPLAY_TIMING_INVALID,
    SAME_BAR_EXECUTION,
    UNADJUSTED_OHLCV_AS_OF,
    UNSUPPORTED_ADJUSTMENT_SEMANTICS,
    ValidationContractError,
    ValidationDatasetManifest,
    canonical_json,
    canonical_manifest_json,
    compute_protocol_semantic_sha256,
    freeze_validation_dataset,
    load_validation_manifest,
    promotion_gate_spec,
    validate_historical_bars,
    validate_replay_input_dates,
    validate_replay_timing,
    validate_sector_evidence,
    validate_universe_evidence,
    validate_ohlcv_evidence,
)


SIGNAL_DATE = "2026-08-28"
SHA = "a" * 64


def _common(source: str) -> dict[str, object]:
    return {
        "source": source,
        "source_version": "2026.08.snapshot-1",
        "temporal_semantics": POINT_IN_TIME,
        "as_of_date": SIGNAL_DATE,
        "known_at": "2026-08-28T16:00:00+08:00",
        "content_sha256": SHA,
    }


def _evidence() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    universe = {
        **_common("exchange-membership-archive"),
        "symbols": ["000001", "600000"],
    }
    sector = {
        **_common("sector-classification-archive"),
        "membership": {"000001": ["银行"], "600000": ["银行"]},
        "rank": {"银行": 3},
        "sector_chg": {"银行": 1.2},
    }
    ohlcv = {
        **_common("ohlcv-archive"),
        "adjustment_semantics": UNADJUSTED_OHLCV_AS_OF,
        "bars": [
            {"date": "2026-08-27", "close": 10.0},
            {"date": SIGNAL_DATE, "close": 10.2},
        ],
    }
    return universe, sector, ohlcv


def test_protocol_semantic_hash_changes_for_rules_but_not_formatting_or_runtime_metadata():
    original = json.loads(canonical_json({"spec": {"rules": ["T only", "T+1"]}}))
    changed = copy.deepcopy(original)
    changed["spec"]["rules"].append("same-bar forbidden")
    assert compute_protocol_semantic_sha256(changed) != compute_protocol_semantic_sha256(original)

    formatted = json.loads(json.dumps(original, indent=4, ensure_ascii=False))
    formatted["created_at"] = "2026-08-28T16:00:00+08:00"
    formatted["retrieved_at"] = "2026-08-28T16:01:00+08:00"
    assert compute_protocol_semantic_sha256(formatted) == compute_protocol_semantic_sha256(original)
    assert len(PROTOCOL_SEMANTIC_SHA256) == 64


def test_freeze_manifest_is_canonical_and_separates_protocol_hash_from_runtime_metadata():
    universe, sector, ohlcv = _evidence()
    manifest = freeze_validation_dataset(
        dataset_version="validation-fixture-v1",
        market="CN_STOCKS",
        symbol="000001",
        date_range={"end": SIGNAL_DATE, "start": "2026-08-27"},
        universe=universe,
        sector=sector,
        ohlcv=ohlcv,
        content_sha256=SHA,
        created_at="2026-08-28T17:00:00+08:00",
        retrieved_at="2026-08-28T16:01:00+08:00",
    )
    assert manifest.signal_date == SIGNAL_DATE
    assert manifest.protocol_semantic_sha256 == PROTOCOL_SEMANTIC_SHA256
    assert manifest.manifest_sha256 == manifest.to_dict()["manifest_sha256"]
    assert canonical_manifest_json(manifest) == canonical_manifest_json(manifest.to_dict())

    later = freeze_validation_dataset(
        dataset_version="validation-fixture-v1",
        market="CN_STOCKS",
        symbol="000001",
        date_range={"start": "2026-08-27", "end": SIGNAL_DATE},
        universe=universe,
        sector=sector,
        ohlcv=ohlcv,
        content_sha256=SHA,
        created_at="2026-08-29T09:00:00+08:00",
        retrieved_at="2026-08-29T09:01:00+08:00",
    )
    assert later.protocol_semantic_sha256 == manifest.protocol_semantic_sha256
    assert later.manifest_sha256 != manifest.manifest_sha256


def test_manifest_round_trip_and_hash_mismatch_fail_safe(tmp_path):
    universe, sector, ohlcv = _evidence()
    manifest = freeze_validation_dataset(
        dataset_version="validation-fixture-v1",
        market="CN_STOCKS",
        symbol="000001",
        date_range=("2026-08-27", SIGNAL_DATE),
        universe=universe,
        sector=sector,
        ohlcv=ohlcv,
        content_sha256=SHA,
        created_at="2026-08-28T17:00:00+08:00",
        retrieved_at="2026-08-28T16:01:00+08:00",
    )
    path = tmp_path / "validation" / "manifest.json"
    path.parent.mkdir()
    path.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    loaded = load_validation_manifest(path, validation_root=tmp_path / "validation")
    assert loaded.manifest_sha256 == manifest.manifest_sha256

    corrupted = manifest.to_dict()
    corrupted["manifest_sha256"] = "b" * 64
    with pytest.raises(ValidationContractError) as error:
        ValidationDatasetManifest.from_dict(corrupted)
    assert error.value.status == MANIFEST_HASH_MISMATCH


@pytest.mark.parametrize(
    ("field", "value", "status"),
    [
        ("schema_version", "wrong-schema", MANIFEST_SCHEMA_VERSION_INVALID),
        ("schema_version", None, MANIFEST_SCHEMA_VERSION_INVALID),
        ("protocol_version", "wrong-protocol", MANIFEST_PROTOCOL_VERSION_INVALID),
        ("protocol_version", None, MANIFEST_PROTOCOL_VERSION_INVALID),
    ],
)
def test_manifest_requires_exact_schema_and_protocol_versions(field, value, status):
    universe, sector, ohlcv = _evidence()
    manifest = freeze_validation_dataset(
        dataset_version="validation-fixture-v1",
        market="CN_STOCKS",
        symbol="000001",
        date_range=("2026-08-27", SIGNAL_DATE),
        universe=universe,
        sector=sector,
        ohlcv=ohlcv,
        content_sha256=SHA,
        created_at="2026-08-28T17:00:00+08:00",
        retrieved_at="2026-08-28T16:01:00+08:00",
    )
    payload = manifest.to_dict()
    if value is None:
        del payload[field]
    else:
        payload[field] = value
    with pytest.raises(ValidationContractError) as error:
        ValidationDatasetManifest.from_dict(payload)
    assert error.value.status == status


def test_current_universe_backfill_is_rejected():
    universe, _, _ = _evidence()
    universe["temporal_semantics"] = "LIVE_OBSERVED"
    with pytest.raises(ValidationContractError) as error:
        validate_universe_evidence(universe, signal_date=SIGNAL_DATE)
    assert error.value.status == CURRENT_DATA_BACKFILL


def test_future_universe_and_misaligned_sector_are_rejected():
    universe, sector, _ = _evidence()
    future_universe = {**universe, "as_of_date": "2026-08-31"}
    with pytest.raises(ValidationContractError) as error:
        validate_universe_evidence(future_universe, signal_date=SIGNAL_DATE)
    assert error.value.status == FUTURE_DATA_INPUT

    old_sector = {**sector, "as_of_date": "2026-08-27"}
    with pytest.raises(ValidationContractError) as error:
        validate_sector_evidence(old_sector, signal_date=SIGNAL_DATE)
    assert error.value.status == INPUT_DATE_MISMATCH


def test_missing_sector_payload_fails_without_rank_or_change_fallback():
    _, sector, _ = _evidence()
    del sector["sector_chg"]
    with pytest.raises(ValidationContractError) as error:
        validate_sector_evidence(sector, signal_date=SIGNAL_DATE)
    assert error.value.status == MISSING_POINT_IN_TIME_EVIDENCE


def test_zero_sector_change_is_valid_and_preserved():
    _, sector, _ = _evidence()
    sector["sector_chg"] = {"银行": 0}
    result = validate_sector_evidence(sector, signal_date=SIGNAL_DATE)
    assert result.payload["sector_chg"] == {"银行": 0.0}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("membership", ["银行"]),
        ("membership", {"000001": "银行"}),
        ("membership", {"000001": []}),
        ("rank", {"银行": "3"}),
        ("rank", {"银行": float("nan")}),
        ("rank", {"银行": float("inf")}),
        ("sector_chg", {"银行": {"value": 0}}),
        ("sector_chg", {"银行": float("-inf")}),
    ],
)
def test_sector_rejects_truthy_or_non_finite_invalid_payloads(field, value):
    _, sector, _ = _evidence()
    sector[field] = value
    with pytest.raises(ValidationContractError) as error:
        validate_sector_evidence(sector, signal_date=SIGNAL_DATE)
    assert error.value.status == INVALID_SECTOR_EVIDENCE


def test_sector_rejects_mismatched_or_uncovered_sector_keys():
    _, sector, _ = _evidence()
    sector["sector_chg"] = {"非银行": 0}
    with pytest.raises(ValidationContractError) as error:
        validate_sector_evidence(sector, signal_date=SIGNAL_DATE)
    assert error.value.status == INVALID_SECTOR_EVIDENCE

    _, sector, _ = _evidence()
    sector["membership"] = {"000001": ["不存在的板块"]}
    with pytest.raises(ValidationContractError) as error:
        validate_sector_evidence(sector, signal_date=SIGNAL_DATE)
    assert error.value.status == INVALID_SECTOR_EVIDENCE


def test_provider_qfq_snapshot_is_not_historical_adjustment_semantics():
    _, _, ohlcv = _evidence()
    ohlcv["adjustment_semantics"] = PROVIDER_QFQ_SNAPSHOT
    with pytest.raises(ValidationContractError) as error:
        validate_ohlcv_evidence(ohlcv, signal_date=SIGNAL_DATE)
    assert error.value.status == UNSUPPORTED_ADJUSTMENT_SEMANTICS


def test_adjusted_ohlcv_requires_separate_point_in_time_adjustment_evidence():
    _, _, ohlcv = _evidence()
    ohlcv["adjustment_semantics"] = HISTORICAL_ADJUSTED_AS_OF
    with pytest.raises(ValidationContractError) as error:
        validate_ohlcv_evidence(ohlcv, signal_date=SIGNAL_DATE)
    assert error.value.status == MISSING_POINT_IN_TIME_EVIDENCE


def test_future_bar_and_future_known_at_are_rejected():
    with pytest.raises(ValidationContractError) as error:
        validate_historical_bars(
            [{"date": "2026-08-31", "close": 10}], signal_date=SIGNAL_DATE
        )
    assert error.value.status == FUTURE_DATA_INPUT

    with pytest.raises(ValidationContractError) as error:
        validate_replay_input_dates(
            {"date": SIGNAL_DATE, "known_at": "2026-08-29T09:00:00+08:00"},
            signal_date=SIGNAL_DATE,
        )
    assert error.value.status == FUTURE_DATA_INPUT


def test_replay_timing_forbids_same_bar_and_requires_next_session():
    earliest = next_execution_date(SIGNAL_DATE)
    assert validate_replay_timing(
        signal_date=SIGNAL_DATE, earliest_execution_date=earliest
    ) == earliest
    with pytest.raises(ValidationContractError) as error:
        validate_replay_timing(
            signal_date=SIGNAL_DATE,
            earliest_execution_date=earliest,
            execution_date=SIGNAL_DATE,
        )
    assert error.value.status == SAME_BAR_EXECUTION
    with pytest.raises(ValidationContractError) as error:
        validate_replay_timing(
            signal_date=SIGNAL_DATE,
            earliest_execution_date="2026-09-01",
        )
    assert error.value.status == REPLAY_TIMING_INVALID


def test_final_oos_path_is_rejected_before_read_and_final_oos_source_is_rejected(tmp_path):
    final_path = tmp_path / "final_oos" / "manifest.json"
    final_path.parent.mkdir()
    final_path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValidationContractError) as error:
        load_validation_manifest(final_path, validation_root=tmp_path)
    assert error.value.status == FINAL_OOS_FORBIDDEN

    universe, sector, ohlcv = _evidence()
    universe["source"] = "archive/final_oos/universe"
    with pytest.raises(ValidationContractError) as error:
        freeze_validation_dataset(
            dataset_version="validation-fixture-v1",
            market="CN_STOCKS",
            symbol="000001",
            date_range=("2026-08-27", SIGNAL_DATE),
            universe=universe,
            sector=sector,
            ohlcv=ohlcv,
            content_sha256=SHA,
            created_at="2026-08-28T17:00:00+08:00",
            retrieved_at="2026-08-28T16:01:00+08:00",
        )
    assert error.value.status == FINAL_OOS_FORBIDDEN


def test_promotion_gate_is_evidence_checklist_not_a_score():
    gate = promotion_gate_spec()
    assert gate.strategy_version == LEGACY_STRATEGY_VERSION
    assert gate.strategy_spec_sha256 == LEGACY_STRATEGY_SPEC_SHA256
    assert "deterministic_replay" in gate.required_evidence
    assert "return" in gate.future_validation_metrics_allowed
    assert gate.to_dict()["phase_2d_computes_results"] is False
    assert gate.to_dict()["score_85_is_predictive_score"] is False
