"""Read a frozen B acquisition package for independent C observations.

This adapter never imports B's evaluator or acquisition client. A B package is
only an input source; missing source bytes and timing evidence remain explicit.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
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
PRICE_PROTOCOL = "C_QFQ_INPUT_V1"
PRICE_OBSERVATION_VOLUME_UNVERIFIED = "PRICE_OBSERVATION_VOLUME_UNVERIFIED"


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _b_kline_sha(value: Any) -> str:
    # generation_contract.KlineManifest hashes normalized JSON without a trailing newline.
    return sha256_bytes(_canonical(value).rstrip(b"\n"))


def _verify_generation_identity(package: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    identity = package.get("generation_identity_payload")
    if (not isinstance(identity, dict)
            or identity.get("input_fingerprint") != manifest.get("input_fingerprint")
            or identity.get("input_coverage") != (manifest.get("provider_version_metadata") or {}).get("input_coverage")
            or identity.get("display_names") != package.get("display_names")
            or identity.get("market_env") != package.get("market_env")
            or sha256_bytes(_canonical(identity)) != package.get("generation_fingerprint")):
        raise CaptureError("B_GENERATION_IDENTITY_MISMATCH", "B generation identity is inconsistent")
    context = manifest.get("run_context") or {}
    universe = manifest.get("universe") or {}
    quotes = manifest.get("quote_snapshot") or {}
    stock = manifest.get("stock_klines") or []
    index = manifest.get("index") or {}
    sector = manifest.get("sector") or {}
    payload = {
        "as_of_date": context.get("as_of_date"), "calendar": context.get("calendar"),
        "mode": context.get("mode"), "timezone": context.get("timezone"),
        "universe_hash": universe.get("content_sha256"),
        "universe_scope": {"name": universe.get("universe_scope"), "version": universe.get("universe_scope_version")},
        "quote_hash": quotes.get("content_sha256"),
        "stock_kline_hashes": {item["symbol"]: item["normalized_data_sha256"] for item in stock},
        "index_hash": index.get("normalized_data_sha256"), "sector_hash": sector.get("content_sha256"),
        "adjustment_mode": sorted({item["adjustment_mode"] for item in [*stock, index]}),
        "temporal_semantics": {
            "universe": universe.get("temporal_semantics"), "quotes": quotes.get("temporal_semantics"),
            "stock_klines": {item["symbol"]: item["temporal_semantics"] for item in stock},
            "index": index.get("temporal_semantics"), "sector": sector.get("temporal_semantics"),
        },
        "provider_version_metadata": {**(context.get("provider_version_metadata") or {}),
                                      **(manifest.get("provider_version_metadata") or {})},
        "providers": {
            "universe": universe.get("source"), "quotes": quotes.get("provider"),
            "stock_klines": {item["symbol"]: item["provider"] for item in stock},
            "index": index.get("provider"), "sector": sector.get("source"),
        },
    }
    if _b_kline_sha(payload) != manifest.get("input_fingerprint"):
        raise CaptureError("B_GENERATION_MANIFEST_HASH_MISMATCH", "B generation manifest fingerprint differs")


def _record(target_date: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    root = _safe_output_root()
    digest = sha256_bytes(_canonical(payload))
    path = root / "shared_input" / target_date.replace("-", "") / f"{digest}.json"
    _write_immutable_json(path, payload)
    return {"status": payload["status"], "record": str(path.relative_to(root)), "record_sha256": digest,
            "gaps": payload["gaps"], "observation_count": len(payload["observations"])}


def _verify_handoff(package_path: Path, receipt_path: Path, *, target_date: str,
                    package_sha256: str, handoff_manifest_sha256: str) -> dict[str, Any]:
    if len(handoff_manifest_sha256) != 64 or any(c not in "0123456789abcdef" for c in handoff_manifest_sha256):
        raise CaptureError("B_HANDOFF_IDENTITY_REQUIRED", "exact handoff manifest SHA is required")
    manifest_path = package_path.parent / "handoff.json"
    raw = manifest_path.read_bytes()
    if sha256_bytes(raw) != handoff_manifest_sha256:
        raise CaptureError("B_HANDOFF_MANIFEST_SHA_MISMATCH", "handoff manifest differs from selected identity")
    manifest = json.loads(raw)
    receipt = json.loads(receipt_path.read_bytes())
    if (manifest.get("schema_version") != "B_C_READONLY_HANDOFF_V1"
            or manifest.get("status") != "EXPORTED_LOCAL_UNVERIFIED_REMOTE"
            or manifest.get("target_date") != target_date
            or manifest.get("package_sha256") != package_sha256
            or receipt.get("schema_version") != "B_C_HANDOFF_RECEIPT_V1"
            or receipt.get("status") != "HANDOFF_VERIFIED"
            or receipt.get("local_export") != "SUCCESS"
            or receipt.get("private_persistence") != "READBACK_VERIFIED"
            or receipt.get("independent_download") != "SUCCESS"
            or receipt.get("per_file_sha_and_bytes") != "VERIFIED"
            or receipt.get("target_date") != target_date
            or receipt.get("package_sha256") != package_sha256
            or receipt.get("handoff_manifest_sha256") != handoff_manifest_sha256
            or receipt.get("generation_fingerprint") != manifest.get("generation_fingerprint")
            or receipt.get("exported_at_bjt") != manifest.get("exported_at_bjt")
            or receipt.get("files") != manifest.get("files")
            or not all(isinstance(receipt.get(key), str) and receipt[key]
                       for key in ("repository", "tag", "asset", "archive_sha256", "download_verified_at_bjt"))):
        raise CaptureError("B_HANDOFF_IDENTITY_MISMATCH", "handoff receipt and manifest identities differ")
    for item in manifest["files"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise CaptureError("B_HANDOFF_FILE_INVALID", "handoff file path escapes package directory")
        data = (package_path.parent / relative).read_bytes()
        if len(data) != item["bytes"] or sha256_bytes(data) != item["sha256"]:
            raise CaptureError("B_HANDOFF_FILE_HASH_MISMATCH", f"handoff file differs: {relative}")
    return {"manifest_sha256": handoff_manifest_sha256, "receipt_sha256": sha256_bytes(receipt_path.read_bytes()),
            "local_export": "SUCCESS", "private_persistence": "READBACK_VERIFIED",
            "independent_download": "SUCCESS", "c_consumption": "SUCCESS",
            "repository": receipt["repository"], "tag": receipt["tag"], "asset": receipt["asset"],
            "archive_sha256": receipt["archive_sha256"],
            "exported_at_bjt": receipt.get("exported_at_bjt"),
            "download_verified_at_bjt": receipt["download_verified_at_bjt"]}


def _price_only_observation(symbol: str, target_date: str, bars: Sequence[Mapping[str, Any]],
                            rule: str) -> dict[str, Any]:
    observation = _rule_observation(symbol=symbol, target_date=target_date, bars=bars, rule_id=rule)
    observation["price_structure_match"] = observation.get("entry_candidate") is True
    observation["price_structure_event_identity"] = observation.get("event_identity")
    observation["entry_candidate"] = False
    observation["event_identity"] = None
    if observation.get("status") == "OBSERVATION_RECORDED":
        observation["status"] = "PRICE_OBSERVATION_ONLY"
    observation["data_quality_status"] = "PARTIAL_UNVERIFIED"
    observation["price_protocol"] = PRICE_PROTOCOL
    observation["volume_observation"] = {
        "status": "PARTIAL_UNVERIFIED", "source": "HiThink historical PriceBarItem.volume",
        "raw_t_day_volume": bars[-1].get("volume"), "declared_unit": "shares",
        "forward_adjustment_effect": "UNRESOLVED",
        "volume_confirmation_valid": False,
    }
    return observation


def consume_b_input(package_path: str | Path, *, target_date: str, expected_sha256: str,
                    handoff_receipt_path: str | Path, expected_handoff_manifest_sha256: str,
                    evidence_root: str | Path | None = None, read_at: datetime | None = None) -> dict[str, Any]:
    """Verify B bytes read-only, evaluate C rules, and persist a C-only result."""
    if not isinstance(target_date, str) or len(target_date) != 10 or date.fromisoformat(target_date).isoformat() != target_date:
        raise ValueError("canonical target T is required")
    now = (read_at or datetime.now(_BJT)).astimezone(_BJT)
    gaps: list[str] = []
    observations: list[dict[str, Any]] = []
    identity: dict[str, Any] = {"adapter_version": ADAPTER_VERSION, "target_date": target_date,
                                "price_protocol": PRICE_PROTOCOL,
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
        identity["handoff"] = _verify_handoff(Path(package_path), Path(handoff_receipt_path),
                                                target_date=target_date, package_sha256=actual,
                                                handoff_manifest_sha256=expected_handoff_manifest_sha256)
        for key in ("exported_at_bjt", "download_verified_at_bjt"):
            value = identity["handoff"].get(key)
            if not isinstance(value, str):
                raise CaptureError("B_HANDOFF_TIME_UNVERIFIED", f"handoff {key} is missing")
            when = datetime.fromisoformat(value)
            if when.tzinfo is None or when.astimezone(_BJT).date().isoformat() != target_date:
                raise CaptureError("B_HISTORICAL_HANDOFF", f"handoff {key} is not on target T")
            if when.astimezone(_BJT) > now:
                raise CaptureError("C_READ_BEFORE_B_HANDOFF", f"C read precedes {key}")
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
        if "generation_identity_payload" in package:
            _verify_generation_identity(package, manifest)
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
        exported_time = datetime.fromisoformat(identity["handoff"]["exported_at_bjt"]).astimezone(_BJT)
        verified_time = datetime.fromisoformat(identity["handoff"]["download_verified_at_bjt"]).astimezone(_BJT)
        if not acquired_time <= exported_time <= verified_time <= now:
            raise CaptureError("B_HANDOFF_TIME_UNVERIFIED", "B acquisition, export, readback and C read are out of order")
        # Export time is an independently read-back durable handoff bound.
        # The runner start time above never substitutes for response timing.
        identity["b_generation_fingerprint"] = package.get("generation_fingerprint")
        handoff_manifest = json.loads((Path(package_path).parent / "handoff.json").read_bytes())
        if handoff_manifest.get("generation_fingerprint") != package.get("generation_fingerprint"):
            raise CaptureError("B_HANDOFF_IDENTITY_MISMATCH", "handoff generation fingerprint differs")
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
        coverage = (manifest.get("provider_version_metadata") or {}).get("input_coverage") or {}
        if coverage != provenance.get("input_coverage") or coverage.get("evaluated_symbol_count") != len(symbols):
            raise CaptureError("B_INPUT_COVERAGE_MISMATCH", "B input coverage does not match evaluated symbols")
        excluded = coverage.get("excluded_symbols")
        if not isinstance(excluded, list) or coverage.get("excluded_symbol_count") != len(excluded):
            raise CaptureError("B_INPUT_COVERAGE_MISMATCH", "B excluded-symbol evidence is incomplete")
        if len(set(symbols)) != len(symbols) or any(item.get("symbol") in symbols for item in excluded if isinstance(item, dict)):
            raise CaptureError("B_INPUT_COVERAGE_MISMATCH", "B evaluated and isolated symbols overlap")
        identity["b_input_coverage"] = coverage
        identity["coverage_groups"] = {
            "b_evaluated_symbols": list(symbols),
            "b_input_isolated": list(excluded),
            "c_rule_or_st_excluded": [],
            "c_st_evidence_unresolved": [],
        }
        if excluded:
            gaps.append("B_INPUT_FAILURE_ISOLATED_SYMBOLS_MISSING_FROM_C_HISTORY")
        identity["b_broad_source_row_count"] = quality.get("source_row_count")
        identity["b_qualified_main_board_count"] = quality.get("retained_count")
        identity["b_evaluated_symbol_count"] = len(symbols)
        if not isinstance(quality.get("source_row_count"), int) or quality["source_row_count"] < len(symbols):
            gaps.append("B_BROAD_UNIVERSE_COVERAGE_UNVERIFIED")
        if isinstance(quality.get("retained_count"), int) and quality["retained_count"] != len(symbols):
            gaps.append("B_QUALIFIED_SYMBOLS_EXCLUDED_FROM_EVALUATION_PACKAGE")
        captures = (provenance.get("evidence_capture") or {}).get("captures") or []
        response_times: dict[str, datetime] = {}
        ticker_names: dict[str, str] = {}
        ticker_received: dict[str, datetime] = {}
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
                sidecar = path.with_suffix(".json")
                if not path.is_file() or not sidecar.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item.get("file_sha256"):
                    gaps.append("B_RAW_SOURCE_SHA_UNVERIFIED")
                    continue
                metadata = json.loads(sidecar.read_bytes())
                if (metadata.get("file_sha256") != item.get("file_sha256")
                        or metadata.get("byte_length") != path.stat().st_size
                        or metadata.get("logical_component_identity") != logical
                        or metadata.get("source_identity") != item.get("source_identity")):
                    gaps.append("B_RAW_SOURCE_SIDECAR_UNVERIFIED")
                    continue
                if component == "hithink_response":
                    try:
                        response_body = json.loads(path.read_bytes())
                        if response_body.get("code") != 0 or not isinstance(response_body.get("data"), dict):
                            raise ValueError("unsuccessful response")
                    except (TypeError, ValueError):
                        gaps.append("B_PROVIDER_RESPONSE_UNVERIFIED")
                        continue
                    requested, received = metadata.get("requested_at_bjt"), metadata.get("received_at_bjt")
                    try:
                        start = datetime.fromisoformat(requested)
                        end = datetime.fromisoformat(received)
                        if start.tzinfo is None or end.tzinfo is None:
                            raise ValueError("time zone missing")
                        start, end = start.astimezone(_BJT), end.astimezone(_BJT)
                        if (start.date().isoformat() != target_date or
                                start < default_calendar().session_close(target_date).astimezone(_BJT) or
                                end < start or end > exported_time):
                            raise ValueError("out of window")
                    except (TypeError, ValueError):
                        gaps.append("B_PROVIDER_REQUEST_TIME_UNVERIFIED")
                        continue
                    if metadata.get("source_identity") == "/api/meta/tickers/list":
                        try:
                            rows = response_body["data"]["item"]
                            for row in rows:
                                symbol = str(row["ticker"])
                                ticker_names[symbol] = str(row["name"])
                                ticker_received[symbol] = end
                        except (KeyError, TypeError, ValueError):
                            gaps.append("B_T_DAY_ST_SOURCE_UNVERIFIED")
                    elif metadata.get("source_identity") == "/api/a-share/prices/historical":
                        for symbol in symbols:
                            if f"thscode={symbol}." in str(metadata.get("request_identity")):
                                response_times[symbol] = end
            identity["b_raw_capture_count"] = len(captures)
        if not ticker_received:
            gaps.append("B_T_DAY_ST_SOURCE_UNVERIFIED")
        for symbol in symbols:
            item = by_symbol[symbol]
            if item.get("as_of_date") != target_date or item.get("provider") != "HiThink Financial-API":
                gaps.append(f"B_HISTORY_SOURCE_OR_DATE_INCOMPATIBLE:{symbol}")
                continue
            if _b_kline_sha({"symbol": symbol, "bars": item.get("bars")}) != item.get("normalized_data_sha256"):
                raise CaptureError("B_KLINE_HASH_MISMATCH", f"B Kline hash mismatch for {symbol}")
            bars = validate_ohlcv_bars(item.get("bars", []))
            if len(bars) < _MIN_HISTORY_BARS or bars[-1]["date"] != target_date or any(bar["date"] >= target_date for bar in bars[:-1]):
                gaps.append(f"B_HISTORY_PREFIX_INCOMPLETE:{symbol}")
                continue
            if item.get("adjustment_mode") != "PROVIDER_QFQ_SNAPSHOT":
                gaps.append(f"B_ADJUSTMENT_UNKNOWN:{symbol}")
                continue
            st_proven = symbol in ticker_received and ticker_names.get(symbol) == names[symbol]
            history_proven = symbol in response_times
            classification = classify_c_universe_row({"symbol": symbol, "name": names[symbol],
                                                       "st_status_known_at_t": st_proven})
            name_classification = classify_c_universe_row({"symbol": symbol, "name": names[symbol],
                                                           "st_status_known_at_t": True})
            if name_classification.get("status") == "EXCLUDED_ST_OR_STAR_ST":
                identity["coverage_groups"]["c_rule_or_st_excluded"].append(
                    {"symbol": symbol, "reason": "ST_NAME_PREFIX" if st_proven else
                     "ST_NAME_PREFIX; T_DAY_TIME_UNVERIFIED"})
            if not history_proven:
                gaps.append(f"B_T_DAY_PRICE_RESPONSE_TIME_UNVERIFIED:{symbol}")
            if classification.get("status") == "UNRESOLVED_ST_STATUS":
                gaps.append(f"B_T_DAY_ST_SOURCE_UNVERIFIED:{symbol}")
                if name_classification.get("status") != "EXCLUDED_ST_OR_STAR_ST":
                    identity["coverage_groups"]["c_st_evidence_unresolved"].append(symbol)
            elif classification.get("status", "").startswith("EXCLUDED_"):
                identity["coverage_groups"]["c_rule_or_st_excluded"].append(symbol)
            # B's name alone is not verified T-day ST evidence. Keep the security
            # in coverage, but do not compute a C rule on an ineligible identity.
            if classification.get("status") != "ELIGIBLE" or not history_proven:
                continue
            observations.append({"symbol": symbol, "name": names[symbol], "b_quote": quotes[symbol],
                                 "t_day_st_evidence": {"source": "HiThink ticker response",
                                                       "received_at_bjt": ticker_received[symbol].isoformat()},
                                 "price_response_received_at_bjt": response_times[symbol].isoformat(),
                                 "b_kline_sha256": item["normalized_data_sha256"],
                                 "price_protocol": PRICE_PROTOCOL,
                                 "price_basis": item["adjustment_mode"],
                                 "volume_basis": "HITHINK_HISTORICAL_VOLUME_SHARES_ADJUSTMENT_UNVERIFIED",
                                 "st_status": classification.get("status"),
                                 "rules": {rule: _price_only_observation(symbol, target_date, bars, rule)
                                           for rule in RULE_CANDIDATES}})
        identity["coverage_status"] = (
            "COMPLETE" if (not excluded and quality.get("retained_count") == len(symbols)
                           and all(symbol in response_times and symbol in ticker_received
                                   and ticker_names.get(symbol) == names[symbol] for symbol in symbols))
            else "PARTIAL_UNVERIFIED"
        )
        identity["volume_semantics"] = "UNRESOLVED"
        if not observations:
            gaps.append("NO_C_RULE_OBSERVATION_FROM_B_INPUT")
        gaps.append("VOLUME_ADJUSTMENT_SEMANTICS_UNRESOLVED")
        status = (PRICE_OBSERVATION_VOLUME_UNVERIFIED
                  if any(rule.get("status") == "PRICE_OBSERVATION_ONLY"
                         for item in observations for rule in item["rules"].values())
                  else C_PARTIAL_UNVERIFIED)
    except (CaptureError, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        status = C_CAPTURE_FAILED
        gaps.append(exc.status if isinstance(exc, CaptureError) else f"B_INPUT_READ_OR_SCHEMA_FAILED:{type(exc).__name__}")
    payload = {"schema_version": ADAPTER_VERSION, "status": status, "source": identity,
               "price_protocol": PRICE_PROTOCOL,
               "gaps": sorted(set(gaps)), "observations": observations,
               "outcome_accessed": False, "return_accessed": False,
               "prospective_captured": False}
    return _record(target_date, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b-input-package", required=True, type=Path)
    parser.add_argument("--b-input-sha256", required=True)
    parser.add_argument("--b-handoff-manifest-sha256", required=True)
    parser.add_argument("--b-handoff-receipt", required=True, type=Path)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--b-evidence-root", type=Path)
    args = parser.parse_args()
    result = consume_b_input(args.b_input_package, target_date=args.target_date,
                             expected_sha256=args.b_input_sha256,
                             handoff_receipt_path=args.b_handoff_receipt,
                             expected_handoff_manifest_sha256=args.b_handoff_manifest_sha256,
                             evidence_root=args.b_evidence_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {C_PARTIAL_UNVERIFIED, PRICE_OBSERVATION_VOLUME_UNVERIFIED} else 1


if __name__ == "__main__":
    raise SystemExit(main())
