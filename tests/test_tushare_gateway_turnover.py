from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import tushare_gateway_turnover as gateway


def _payload(rows):
    return {
        "response": {
            "columns": ["ts_code", "trade_date", "turnover_rate", "float_share"],
            "rows": rows,
        },
        "response_row_count": len(rows),
    }


def test_symbol_and_date_mapping_is_strict_and_lowercase():
    assert gateway._canonical_symbol("000001.SZ") == "000001.sz"
    assert gateway._canonical_symbol("600000.SH") == "600000.sh"
    assert gateway._canonical_symbol("920001.BJ") is None
    assert gateway._date_text(20260105) == "2026-01-05"


def test_schema_audit_rejects_date_mismatch_and_duplicate():
    rows = [{"ts_code": "000001.SZ", "trade_date": "2026-01-05", "turnover_rate": 1.0, "float_share": 100.0}]
    assert gateway._schema_audit(_payload(rows), "2026-01-05", strict_unique=True)["status"] == "PASS"
    with pytest.raises(RuntimeError, match="trade_date mismatch"):
        gateway._schema_audit(_payload([{**rows[0], "trade_date": "2026-01-06"}]), "2026-01-05", strict_unique=True)
    with pytest.raises(RuntimeError, match="duplicate ts_code"):
        gateway._schema_audit(_payload(rows + rows), "2026-01-05", strict_unique=True)


def test_conflicting_duplicate_canonical_rows_fail_closed():
    rows = [
        {"ts_code": "000001.SZ", "trade_date": "2026-01-05", "turnover_rate": 1.0, "float_share": 100.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-01-05", "turnover_rate": 1.1, "float_share": 100.0},
    ]
    with pytest.raises(RuntimeError, match="conflicting duplicate"):
        gateway._schema_audit(_payload(rows), "2026-01-05", strict_unique=False)


def test_semantics_formula_accepts_percent_and_wan_shares():
    store = {
        "bounds": {"000001.sz": (0, 1)},
        "date_ms": [20260105],
        "volume": [100000.0],
    }
    payloads = {"2026-01-05": _payload([{
        "ts_code": "000001.SZ",
        "trade_date": "2026-01-05",
        "turnover_rate": 1.0,
        "float_share": 1000.0,
    }])}
    with pytest.raises(RuntimeError, match="fewer than 100"):
        gateway._semantics_audit(payloads, store, {"2026-01-05": 20260105})


def test_checkpoint_template_never_persists_token():
    checkpoint = gateway._checkpoint_template(["2026-01-05"], Path("raw"), "pilot")
    assert checkpoint["credential_present"] is True
    assert checkpoint["token_persisted"] is False
    assert "TUSHARE_GATEWAY_TOKEN" not in str(checkpoint)


def _diagnostic_record(index: int, *, turnover: float | None = None, relative_volume: float | None = None):
    return {
        "symbol": f"{index:06d}.sz",
        "signal_date": f"2024-01-{index + 1:02d}",
        "turnover_rate_pct": float(index) if turnover is None else turnover,
        "relative_volume": float(index) if relative_volume is None else relative_volume,
        "outcomes": {
            "5D": {"status": "AVAILABLE", "return_pct": float(index), "mfe_pct": 1.0, "mae_pct": -1.0},
            "10D": {"status": "AVAILABLE", "return_pct": float(index) + 0.5, "mfe_pct": 2.0, "mae_pct": -2.0},
        },
    }


def test_joint_top_one_percent_is_deterministic_and_exact_intersection():
    records = [_diagnostic_record(index) for index in range(150)]
    records[147]["relative_volume"] = 1000.0
    records[148]["relative_volume"] = -1.0

    first = gateway._joint_top_one_percent(records)
    second = gateway._joint_top_one_percent(records)

    turnover_membership = gateway._top_one_percent_membership(records, "turnover_rate_pct")
    relative_volume_membership = gateway._top_one_percent_membership(records, "relative_volume")
    assert turnover_membership == {148, 149}
    assert relative_volume_membership == {147, 149}
    assert gateway._joint_top_one_percent_membership(records) == turnover_membership & relative_volume_membership == {149}
    assert first == second
    assert first["intersection_rows"] == 1
    assert first["joint"]["5D"]["n"] == 1


def test_joint_check_does_not_change_individual_top_one_percent_membership():
    records = [_diagnostic_record(index) for index in range(150)]
    expected = {
        "turnover_rate_pct": gateway._top_one_percent_membership(records, "turnover_rate_pct"),
        "relative_volume": gateway._top_one_percent_membership(records, "relative_volume"),
    }

    gateway._joint_top_one_percent(records)

    assert gateway._top_one_percent_membership(records, "turnover_rate_pct") == expected["turnover_rate_pct"]
    assert gateway._top_one_percent_membership(records, "relative_volume") == expected["relative_volume"]
    assert gateway._top_one_percent(records, "turnover_rate_pct")["top_rows"] == len(expected["turnover_rate_pct"])
    assert gateway._top_one_percent(records, "relative_volume")["top_rows"] == len(expected["relative_volume"])


def test_decision_audit_includes_preregistered_joint_top_one_percent_check():
    summary_path = Path("data/validation/b_turnover_x_relative_volume_incremental_v1/tushare_gateway/manifest/diagnostic_summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    audit = summary["decision_audit"]
    joint = summary["top_one_percent"]["joint_intersection"]

    assert "joint_top_one_percent_coherent" in audit
    assert "pre_registered_top_one_percent_checks" in audit
    assert audit["pre_registered_top_one_percent_checks"]["joint_intersection"]["intersection_rows"] == joint["intersection_rows"]
    assert audit["pre_registered_top_one_percent_checks"]["joint_intersection"]["comparison_baseline"] == joint["comparison_baseline"]["name"]
