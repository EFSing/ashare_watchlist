from __future__ import annotations

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
