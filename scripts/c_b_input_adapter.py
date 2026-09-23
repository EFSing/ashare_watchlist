"""Read a frozen B acquisition package for independent C observations.

This adapter never imports B's evaluator or acquisition client. A B package is
only an input source; missing source bytes and timing evidence remain explicit.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from c_pre_outcome_design import RULE_CANDIDATES, classify_c_universe_row, validate_ohlcv_bars
from c_prospective_capture import (
    C_PARTIAL_UNVERIFIED, C_CAPTURE_FAILED, CaptureError, _MIN_HISTORY_BARS,
    _rule_observation, _safe_output_root, _write_immutable_json, sha256_bytes,
)
from trading_calendar import default_calendar

_BJT = timezone(timedelta(hours=8))
ADAPTER_VERSION = "C_B_FROZEN_INPUT_READER_V1"
PACKAGE_SCHEMA = "CANDIDATE_BOUND_LIVE_INPUT_PACKAGE_V4"


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _record(target_date: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    root = _safe_output_root()
    digest = sha256_bytes(_canonical(payload))
    path = root / "shared_input" / target_date.replace("-", "") / f"{digest}.json"
    _write_immutable_json(path, payload)
    return {"status": payload["status"], "record": str(path.relative_to(root)), "record_sha256": digest,
            "gaps": payload["gaps"], "observation_count": len(payload["observations"])}


def consume_b_input(package_path: str | Path, *, target_date: str, expected_sha256: str,
                    evidence_root: str | Path | None = None, read_at: datetime | None = None) -> dict[str, Any]:
    """Verify B bytes read-only, evaluate C rules, and persist a C-only result."""
    now = (read_at or datetime.now(_BJT)).astimezone(_BJT)
    gaps: list[str] = []
    observations: list[dict[str, Any]] = []
    identity: dict[str, Any] = {"adapter_version": ADAPTER_VERSION, "target_date": target_date,
                                "c_read_at_bjt": now.isoformat(timespec="seconds"),
                                "b_package_expected_sha256": expected_sha256,
                                "b_package_actual_sha256": None,
                                "b_acquired_at_bjt": None, "b_persisted_at_bjt": None}
    try:
        if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
            raise CaptureError("B_PACKAGE_SHA_REQUIRED", "expected B package SHA-256 is invalid")
        raw = Path(package_path).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        identity["b_package_actual_sha256"] = actual
        if actual != expected_sha256:
            raise CaptureError("B_PACKAGE_SHA_MISMATCH", "B package bytes differ from expected SHA-256")
        package = json.loads(raw)
        if not isinstance(package, dict) or package.get("schema_version") != PACKAGE_SCHEMA:
            raise CaptureError("B_FULL_INPUT_MISSING", "source is not a complete B input package")
        content = dict(package)
        declared = content.pop("content_sha256", None)
        if declared != sha256_bytes(_canonical(content)):
            raise CaptureError("B_PACKAGE_CONTENT_HASH_MISMATCH", "B package content identity differs")
        manifest = package.get("generation_input_manifest")
        if not isinstance(manifest, dict) or manifest.get("status") != "READY_FOR_STRATEGY_EVALUATION":
            raise CaptureError("B_FULL_INPUT_MISSING", "B input manifest is not READY")
        if manifest.get("signal_date") != target_date or package.get("market_env", {}).get("as_of_date") != target_date:
            raise CaptureError("B_TARGET_DATE_MISMATCH", "B input date differs from target T")
        if not default_calendar().is_trading_day(target_date):
            raise CaptureError("B_TARGET_DATE_INVALID", "target T is not an XSHG session")
        provenance = package.get("provenance") or {}
        acquired = provenance.get("retrieved_at_bjt")
        if not isinstance(acquired, str):
            raise CaptureError("B_ACQUISITION_TIME_MISSING", "B package lacks acquisition time")
        acquired_time = datetime.fromisoformat(acquired)
        if acquired_time.tzinfo is None:
            raise CaptureError("B_ACQUISITION_TIME_INVALID", "B acquisition time lacks zone")
        acquired_time = acquired_time.astimezone(_BJT)
        identity["b_acquired_at_bjt"] = acquired_time.isoformat()
        if acquired_time.date().isoformat() != target_date or acquired_time < default_calendar().session_close(target_date).astimezone(_BJT):
            raise CaptureError("B_HISTORICAL_OR_PRE_CLOSE_INPUT", "B input was not acquired after T close on T")
        if provenance.get("acquisition_timing") == "AUTHORIZED_WEEKEND_BACKFILL":
            raise CaptureError("B_HISTORICAL_OR_PRE_CLOSE_INPUT", "B weekend backfill is not prospective T input")
        if now < acquired_time:
            raise CaptureError("C_READ_BEFORE_B_ACQUISITION", "C read time precedes B acquisition")
        # B's package records run-start retrieval time, not per-response receive
        # or durable export time. Do not infer those from C's read time or mtime.
        gaps.extend(["B_EXACT_PROVIDER_REQUEST_RECEIVE_TIMES_NOT_PERSISTED",
                     "B_DURABLE_PERSISTENCE_TIME_NOT_PERSISTED"])
        identity["b_generation_fingerprint"] = package.get("generation_fingerprint")
        identity["b_input_fingerprint"] = manifest.get("input_fingerprint")
        universe = manifest.get("universe") or {}
        symbols = universe.get("symbols")
        names = package.get("display_names")
        quotes = (manifest.get("quote_snapshot") or {}).get("quotes")
        klines = manifest.get("stock_klines")
        if not isinstance(symbols, list) or not symbols or not isinstance(names, dict) or not isinstance(quotes, dict) or not isinstance(klines, list):
            raise CaptureError("B_FULL_INPUT_MISSING", "B full universe, names, quotes, or history are absent")
        by_symbol = {item.get("symbol"): item for item in klines if isinstance(item, dict)}
        if len(by_symbol) != len(klines) or set(symbols) != set(names) or set(symbols) != set(quotes) or set(symbols) != set(by_symbol):
            raise CaptureError("B_FULL_INPUT_MISSING", "B per-symbol input coverage is incomplete")
        quality = (manifest.get("provider_version_metadata") or {}).get("universe_quality") or {}
        identity["b_broad_source_row_count"] = quality.get("source_row_count")
        identity["b_qualified_main_board_count"] = quality.get("retained_count")
        identity["b_evaluated_symbol_count"] = len(symbols)
        if quality.get("source_row_count", 0) > len(symbols):
            gaps.append("B_BROAD_UNIVERSE_ROWS_NOT_IN_PACKAGE")
        if isinstance(quality.get("retained_count"), int) and quality["retained_count"] != len(symbols):
            gaps.append("B_QUALIFIED_SYMBOLS_EXCLUDED_FROM_EVALUATION_PACKAGE")
        captures = (provenance.get("evidence_capture") or {}).get("captures") or []
        if not evidence_root or not isinstance(captures, list) or not captures:
            gaps.append("B_RAW_SOURCE_BYTES_NOT_DURABLE")
        else:
            root = Path(evidence_root)
            for item in captures:
                if not isinstance(item, dict) or item.get("completeness_status") != "COMPLETE":
                    gaps.append("B_RAW_SOURCE_CAPTURE_INCOMPLETE")
                    continue
                component, logical = item.get("component"), item.get("logical_component_identity")
                if not isinstance(component, str) or not isinstance(logical, str):
                    gaps.append("B_RAW_SOURCE_CAPTURE_IDENTITY_MISSING")
                    continue
                path = root / target_date.replace("-", "") / component / f"{hashlib.sha256(logical.encode()).hexdigest()}.raw"
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item.get("file_sha256"):
                    gaps.append("B_RAW_SOURCE_SHA_UNVERIFIED")
            identity["b_raw_capture_count"] = len(captures)
        for symbol in symbols:
            item = by_symbol[symbol]
            if item.get("as_of_date") != target_date or item.get("provider") != "HiThink Financial-API":
                gaps.append(f"B_HISTORY_SOURCE_OR_DATE_INCOMPATIBLE:{symbol}")
                continue
            if sha256_bytes(_canonical({"symbol": symbol, "bars": item.get("bars")})) != item.get("normalized_data_sha256"):
                raise CaptureError("B_KLINE_HASH_MISMATCH", f"B Kline hash mismatch for {symbol}")
            bars = validate_ohlcv_bars(item.get("bars", []))
            if len(bars) < _MIN_HISTORY_BARS or bars[-1]["date"] != target_date or any(bar["date"] >= target_date for bar in bars[:-1]):
                gaps.append(f"B_HISTORY_PREFIX_INCOMPLETE:{symbol}")
                continue
            if item.get("adjustment_mode") != "PROVIDER_QFQ_SNAPSHOT":
                gaps.append(f"B_ADJUSTMENT_UNKNOWN:{symbol}")
                continue
            classification = classify_c_universe_row({"symbol": symbol, "name": names[symbol], "st_status_known_at_t": False})
            if classification.get("status") == "UNRESOLVED_ST_STATUS":
                gaps.append(f"B_T_DAY_ST_SOURCE_UNVERIFIED:{symbol}")
            if item.get("adjustment_mode") == "PROVIDER_QFQ_SNAPSHOT":
                gaps.append("B_FORWARD_ADJUSTED_PRICE_INCOMPATIBLE_WITH_C_UNADJUSTED_BASIS")
            observations.append({"symbol": symbol, "name": names[symbol], "b_quote": quotes[symbol],
                                 "b_kline_sha256": item["normalized_data_sha256"],
                                 "price_basis": item["adjustment_mode"], "volume_basis": "UNVERIFIED",
                                 "st_status": classification.get("status"),
                                 "rules": {rule: _rule_observation(symbol=symbol, target_date=target_date, bars=bars, rule_id=rule)
                                           for rule in RULE_CANDIDATES}})
        if not observations:
            gaps.append("NO_C_RULE_OBSERVATION_FROM_B_INPUT")
        status = C_PARTIAL_UNVERIFIED
    except (CaptureError, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        status = C_CAPTURE_FAILED
        gaps.append(exc.status if isinstance(exc, CaptureError) else f"B_INPUT_READ_OR_SCHEMA_FAILED:{type(exc).__name__}")
    payload = {"schema_version": ADAPTER_VERSION, "status": status, "source": identity,
               "gaps": sorted(set(gaps)), "observations": observations,
               "outcome_accessed": False, "return_accessed": False,
               "prospective_captured": False}
    return _record(target_date, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b-input-package", required=True, type=Path)
    parser.add_argument("--b-input-sha256", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--b-evidence-root", type=Path)
    args = parser.parse_args()
    result = consume_b_input(args.b_input_package, target_date=args.target_date,
                             expected_sha256=args.b_input_sha256, evidence_root=args.b_evidence_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == C_PARTIAL_UNVERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())
