# -*- coding: utf-8 -*-
"""Recover fixed-date review nodes from one immutable local evidence package.

This module is intentionally file-only.  It imports the Tencent parser but
never calls the Tencent transport.  The recovery exception is narrow: an
exactly captured T-close quote may populate a same-date execution observation
or fixed-date horizon node, while it may not reconstruct any missing path day.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from data_paths import DataPaths
from tencent_quotes import parse_quote_response
from trading_calendar import TradingCalendar, default_calendar
from watchlist_schema import load_watchlist


CAPTURE_SCHEMA = "T_CLOSE_SOURCE_CAPTURE_V1"
RECOVERY_SOURCE_MODE = "EXACT_DATE_IMMUTABLE_EVIDENCE_RECOVERY_V1"
TARGET_DATE = "2026-09-08"
EXPECTED_CODE_GIT_SHA = "52484a82e4a2700372c85c47991f62717d4b1196"
EXPECTED_PACKAGE_SHA256 = "d3bbdc7275fe32fd8763eba03fb987fad2308eb43d6149919829b0d5ec462ba4"
EXPECTED_PACKAGE_CONTENT_SHA256 = "142efea5385d22781f94b6d43cb836e01901e863081c1ec4f49283ae93972df9"
EXPECTED_GENERATION_FINGERPRINT = "93882eecb2f37d4c0653864bd54dbbe80c19334b7913439ef3f6939a69ef5db8"
EXPECTED_STRATEGY = "B_BREAKOUT_RETEST_LEGACY_V1_1"

WATCHLIST_SPECS = {
    "2026-09-03": {
        "count": 11,
        "sha256": "50f0717e55daaf4435e1d25b4f1d029109c566d72d63a1fc566f263cdf0fb085",
    },
    "2026-09-07": {
        "count": 25,
        "sha256": "5a99273b6304621acbf7bba2423a6e372668348a31ac436021caf5f5855db100",
    },
    "2026-09-08": {
        "count": 34,
        "sha256": "f58059cd5269f8ac5cd10da357a2bd008a76ef84feaa399846d74ad7daa4b5fc",
    },
}

_FORMAL_PROVIDER_SOURCES = {
    "hithink_kline": {
        ("HiThink Financial-API", "/api/a-share/prices/historical"),
        ("HiThink Financial-API", "/api/a-share-index/prices/historical"),
    },
    "hithink_response": {
        ("HiThink Financial-API", "/api/a-share/prices/historical"),
        ("HiThink Financial-API", "/api/a-share-index/prices/historical"),
        ("HiThink Financial-API", "/api/meta/tickers/list"),
    },
    "hithink_universe": {
        ("HiThink Financial-API", "/api/meta/tickers/list"),
    },
    "official_listed_roster": {
        ("AkShare", "https://www.sse.com.cn/assortment/stock/list/share/"),
        ("AkShare", "https://www.szse.cn/market/product/stock/list/index.html"),
    },
    "sina_sector_membership": {
        ("AkShare", "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"),
    },
    "sina_sector_spot": {
        ("AkShare", "http://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php"),
    },
    "tencent_quote": {
        ("Tencent", "qt.gtimg.cn"),
    },
}
_RE_THSCODE = re.compile(r"thscode=(\d{6})\.(?:SH|SZ|BJ)")
_OHLC_FIELDS = ("open", "high", "low", "close")


class ExactDateEvidenceError(ValueError):
    """The immutable package cannot support a safe exact-date recovery."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date_text(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    return datetime.strptime(text, "%Y-%m-%d").date().isoformat()


def _date_token(value: str) -> str:
    return value.replace("-", "")


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def resolve_evidence_root(evidence_root: str | Path, target_date: date | datetime | str) -> Path:
    """Resolve the one deterministic evidence-root layout without probing data alternatives."""

    base = Path(evidence_root).expanduser().resolve()
    token = _date_token(_date_text(target_date))
    candidates: list[Path] = []
    for candidate in (base, base / token, base / token / token):
        candidate = candidate.resolve()
        if candidate not in candidates and (candidate / "tencent_quote").is_dir():
            candidates.append(candidate)
    if len(candidates) != 1:
        raise ExactDateEvidenceError(
            f"EXACT_DATE_EVIDENCE_ROOT_UNRESOLVED: expected one root under {base}, found {len(candidates)}"
        )
    return candidates[0]


def _metadata_errors(
    component: str,
    metadata: Mapping[str, Any],
    raw: bytes,
    target_date: str,
    session_close: datetime,
    expected_code_git_sha: str,
) -> list[str]:
    errors: list[str] = []
    if metadata.get("schema_version") != CAPTURE_SCHEMA:
        errors.append("schema_version")
    if metadata.get("target_date") != target_date:
        errors.append("target_date")
    effective = metadata.get("effective_trading_date")
    if effective is not None and effective != target_date:
        errors.append("effective_trading_date")
    if metadata.get("code_git_sha") != expected_code_git_sha:
        errors.append("code_git_sha")
    if metadata.get("completeness_status") != "COMPLETE":
        errors.append("completeness_status")
    if not metadata.get("provider") or not metadata.get("source_identity"):
        errors.append("provider_source_identity")
    elif (metadata["provider"], metadata["source_identity"]) not in _FORMAL_PROVIDER_SOURCES.get(component, set()):
        errors.append("formal_provider_source")
    if metadata.get("file_sha256") != _sha256_bytes(raw):
        errors.append("file_sha256")
    if metadata.get("byte_length") != len(raw):
        errors.append("byte_length")
    retrieved_text = metadata.get("actual_retrieved_at_bjt")
    if not isinstance(retrieved_text, str):
        errors.append("actual_retrieved_at_bjt")
    else:
        try:
            retrieved = datetime.fromisoformat(retrieved_text)
            if retrieved.tzinfo is None:
                errors.append("retrieved_timezone")
            elif retrieved.astimezone(session_close.tzinfo) < session_close:
                errors.append("retrieved_before_session_close")
            elif retrieved.date().isoformat() != target_date:
                errors.append("retrieved_date")
        except ValueError:
            errors.append("actual_retrieved_at_bjt")
    return errors


def audit_exact_date_evidence(
    evidence_root: str | Path,
    target_date: date | datetime | str = TARGET_DATE,
    *,
    calendar: TradingCalendar | None = None,
    expected_code_git_sha: str = EXPECTED_CODE_GIT_SHA,
    expected_codes: set[str] | None = None,
) -> dict[str, Any]:
    """Audit every capture pair and parse only the local exact-date quote files."""

    normalized_date = _date_text(target_date)
    cal = calendar or default_calendar()
    root = resolve_evidence_root(evidence_root, normalized_date)
    session_close = cal.session_close(normalized_date)
    sidecars = sorted(path for path in root.rglob("*.json") if path.is_file())
    raw_paths = {path for path in root.rglob("*.raw") if path.is_file()}
    seen_raw: set[Path] = set()
    errors: list[str] = []
    component_counts: dict[str, int] = {}
    valid_pairs = 0
    unknown_origin_count = 0
    quotes: dict[str, dict[str, Any]] = {}
    quote_metadata: dict[str, dict[str, Any]] = {}
    kline_records: dict[str, dict[str, Any]] = {}

    for sidecar in sidecars:
        component = sidecar.parent.name
        component_counts[component] = component_counts.get(component, 0) + 1
        raw_path = sidecar.with_suffix(".raw")
        pair_errors: list[str] = []
        if not raw_path.exists():
            pair_errors.append("raw_missing")
            raw = b""
        else:
            seen_raw.add(raw_path)
            try:
                raw = raw_path.read_bytes()
            except OSError:
                raw = b""
                pair_errors.append("raw_unreadable")
        try:
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            metadata = {}
            pair_errors.append("sidecar_unreadable")
        if not isinstance(metadata, dict):
            metadata = {}
            pair_errors.append("sidecar_not_object")
        pair_errors.extend(
            _metadata_errors(
                component,
                metadata,
                raw,
                normalized_date,
                session_close,
                expected_code_git_sha,
            )
        )
        if metadata.get("code_git_sha") == "UNKNOWN_ORIGIN":
            unknown_origin_count += 1
        if component not in _FORMAL_PROVIDER_SOURCES:
            pair_errors.append("unknown_component")

        if component == "tencent_quote" and not pair_errors:
            codes = metadata.get("codes")
            if (
                not isinstance(codes, list)
                or not codes
                or len(codes) != len(set(codes))
                or any(not isinstance(code, str) or not re.fullmatch(r"\d{6}", code) for code in codes)
            ):
                pair_errors.append("codes")
            elif metadata.get("record_count") != len(codes):
                pair_errors.append("record_count")
            else:
                try:
                    encoding = str(metadata.get("decode_encoding") or "gbk")
                    parsed = parse_quote_response(
                        raw.decode(encoding),
                        expected_codes=codes,
                        expected_date=normalized_date,
                    )
                    for code, quote in parsed.items():
                        if code in quotes:
                            pair_errors.append(f"duplicate_quote:{code}")
                        else:
                            quotes[code] = quote
                            quote_metadata[code] = {
                                "component": component,
                                "provider": metadata.get("provider"),
                                "source_identity": metadata.get("source_identity"),
                                "provider_version": metadata.get("provider_version"),
                                "capture_sha256": metadata.get("file_sha256"),
                                "source_capture_sha256": metadata.get("file_sha256"),
                                "capture_path": _relative(sidecar, root),
                                "source_retrieved_at_bjt": metadata.get("actual_retrieved_at_bjt"),
                                "target_date": normalized_date,
                                "code_git_sha": metadata.get("code_git_sha"),
                            }
                except Exception as exc:
                    pair_errors.append(f"quote_parse:{type(exc).__name__}")

        if component == "hithink_kline" and not pair_errors and expected_codes:
            if metadata.get("adjustment_mode") == "PROVIDER_QFQ_SNAPSHOT":
                match = _RE_THSCODE.search(str(metadata.get("logical_component_identity", "")))
                if match and match.group(1) in expected_codes:
                    code = match.group(1)
                    try:
                        records = json.loads(raw.decode(str(metadata.get("encoding") or "utf-8")))
                        if not isinstance(records, list):
                            raise ValueError("records_not_list")
                        if code in kline_records:
                            pair_errors.append(f"duplicate_qfq_kline:{code}")
                        else:
                            kline_records[code] = {
                                "records": records,
                                "metadata": dict(metadata),
                                "capture_path": _relative(sidecar, root),
                            }
                    except Exception as exc:
                        pair_errors.append(f"kline_parse:{type(exc).__name__}")

        if pair_errors:
            if len(errors) < 80:
                errors.append(f"{_relative(sidecar, root)}: {','.join(sorted(set(pair_errors)))}")
        else:
            valid_pairs += 1

    for raw_path in sorted(raw_paths - seen_raw):
        if len(errors) < 80:
            errors.append(f"{_relative(raw_path, root)}: sidecar_missing")

    total_pairs = len(sidecars) + len(raw_paths - seen_raw)
    return {
        "target_date": normalized_date,
        "evidence_root": str(root),
        "integrity_status": "PASS" if not errors else "FAIL",
        "pair_count": total_pairs,
        "valid_pair_count": valid_pairs,
        "invalid_pair_count": max(0, total_pairs - valid_pairs),
        "component_counts": dict(sorted(component_counts.items())),
        "unknown_origin_count": unknown_origin_count,
        "provider_calls": 0,
        "source_access_mode": "LOCAL_IMMUTABLE_FILES_ONLY",
        "errors": errors,
        "quotes": quotes,
        "quote_metadata": quote_metadata,
        "kline_records": kline_records,
    }


def audit_price_compatibility(
    audit: Mapping[str, Any],
    watchlists: Mapping[str, Mapping[str, Any]],
    *,
    target_date: date | datetime | str = TARGET_DATE,
) -> dict[str, Any]:
    """Cross-check raw Tencent OHLC against the captured QFQ bar, without writing data."""

    normalized_date = _date_text(target_date)
    target_codes = sorted({
        str(candidate["code"])
        for watchlist in watchlists.values()
        for candidate in watchlist.get("candidates", [])
    })
    quotes = audit.get("quotes", {})
    klines = audit.get("kline_records", {})
    compatible: list[str] = []
    missing: dict[str, str] = {}
    incompatible: dict[str, str] = {}
    field_matches = {field: 0 for field in _OHLC_FIELDS}
    for code in target_codes:
        quote = quotes.get(code)
        kline = klines.get(code)
        if not quote:
            missing[code] = "EXACT_QUOTE_EVIDENCE_MISSING"
            continue
        if not kline:
            missing[code] = "QFQ_COMPATIBILITY_BAR_MISSING"
            continue
        metadata = kline.get("metadata", {})
        if metadata.get("adjustment_mode") != "PROVIDER_QFQ_SNAPSHOT":
            incompatible[code] = "RECOVERY_PRICE_BASIS_INCOMPATIBLE: adjustment_mode"
            continue
        records = {
            str(record.get("date")): record
            for record in kline.get("records", [])
            if isinstance(record, dict) and record.get("date")
        }
        current = records.get(normalized_date)
        if not current:
            missing[code] = "QFQ_CURRENT_BAR_MISSING"
            continue
        mismatch = []
        for field in _OHLC_FIELDS:
            if quote.get("price") is None and field == "close":
                mismatch.append(field)
                continue
            quote_value = quote.get("price") if field == "close" else quote.get(field)
            if quote_value != current.get(field):
                mismatch.append(field)
            else:
                field_matches[field] += 1
        for list_date, watchlist in watchlists.items():
            for candidate in watchlist.get("candidates", []):
                if str(candidate.get("code")) != code:
                    continue
                signal_bar = records.get(list_date)
                if not signal_bar:
                    mismatch.append(f"signal_bar:{list_date}")
                elif signal_bar.get("close") != candidate.get("price"):
                    mismatch.append(f"signal_price:{list_date}")
        if mismatch:
            incompatible[code] = "RECOVERY_PRICE_BASIS_INCOMPATIBLE: " + ",".join(sorted(set(mismatch)))
        else:
            compatible.append(code)
    status = "PASS" if not incompatible and not missing else "PARTIAL"
    return {
        "status": status,
        "target_date": normalized_date,
        "codes_expected": len(target_codes),
        "codes_compatible": len(compatible),
        "codes_missing": len(missing),
        "codes_incompatible": len(incompatible),
        "compatible_codes": compatible,
        "missing_codes": missing,
        "incompatible_codes": incompatible,
        "field_matches": field_matches,
        "source_basis": "Tencent exact quote; QFQ bar compatibility cross-check only",
    }


def _audit_package(paths: DataPaths, target_date: str) -> dict[str, Any]:
    package_dir = paths.root / "prospective_inputs" / _date_token(target_date)
    candidates = sorted(path for path in package_dir.glob(f"{target_date}_*.json") if path.is_file())
    if len(candidates) != 1:
        raise ExactDateEvidenceError(
            f"EXACT_DATE_PACKAGE_UNRESOLVED: expected one package for {target_date}, found {len(candidates)}"
        )
    package = candidates[0]
    fingerprint = package.stem.split("_", 1)[1] if "_" in package.stem else ""
    if fingerprint != EXPECTED_GENERATION_FINGERPRINT:
        raise ExactDateEvidenceError("EXACT_DATE_PACKAGE_FINGERPRINT_MISMATCH")
    file_sha = _sha256_file(package)
    if file_sha != EXPECTED_PACKAGE_SHA256:
        raise ExactDateEvidenceError("EXACT_DATE_PACKAGE_SHA256_MISMATCH")
    with package.open("rb") as handle:
        header = handle.read(8192).decode("utf-8", errors="replace")
    content_match = re.search(r'"content_sha256"\s*:\s*"([0-9a-f]{64})"', header)
    strategy_match = re.search(r'"strategy_version"\s*:\s*"([^"]+)"', header)
    if not content_match or content_match.group(1) != EXPECTED_PACKAGE_CONTENT_SHA256:
        raise ExactDateEvidenceError("EXACT_DATE_PACKAGE_CONTENT_SHA256_MISMATCH")
    if not strategy_match or strategy_match.group(1) != EXPECTED_STRATEGY:
        raise ExactDateEvidenceError("EXACT_DATE_PACKAGE_STRATEGY_MISMATCH")
    return {
        "path": str(package),
        "file_sha256": file_sha,
        "content_sha256": content_match.group(1),
        "generation_fingerprint": fingerprint,
        "strategy_version": strategy_match.group(1),
    }


def _load_recovery_watchlists(paths: DataPaths) -> dict[str, dict[str, Any]]:
    watchlists: dict[str, dict[str, Any]] = {}
    for list_date, spec in WATCHLIST_SPECS.items():
        path = paths.watchlist_file(list_date)
        if not path.exists():
            raise ExactDateEvidenceError(f"EXACT_DATE_WATCHLIST_MISSING: {list_date}")
        file_sha = _sha256_file(path)
        if file_sha != spec["sha256"]:
            raise ExactDateEvidenceError(f"EXACT_DATE_WATCHLIST_SHA256_MISMATCH: {list_date}")
        watchlist = load_watchlist(path)
        if watchlist.get("date") != list_date or watchlist.get("strategy_version") != EXPECTED_STRATEGY:
            raise ExactDateEvidenceError(f"EXACT_DATE_WATCHLIST_IDENTITY_MISMATCH: {list_date}")
        if len(watchlist.get("candidates", [])) != spec["count"]:
            raise ExactDateEvidenceError(f"EXACT_DATE_WATCHLIST_COUNT_MISMATCH: {list_date}")
        if any(candidate.get("strategy_version") != EXPECTED_STRATEGY for candidate in watchlist["candidates"]):
            raise ExactDateEvidenceError(f"EXACT_DATE_WATCHLIST_STRATEGY_MISMATCH: {list_date}")
        watchlists[list_date] = watchlist
    return watchlists


def _path_complete(
    signal: Mapping[str, Any],
    target_date: date,
    calendar: TradingCalendar,
) -> bool:
    first_trigger = signal.get("first_trigger_date")
    if not signal.get("entry_price") or not first_trigger:
        return False
    first_trigger_day = datetime.strptime(str(first_trigger), "%Y-%m-%d").date()
    if first_trigger_day > target_date:
        return False
    observation_dates = {
        str(observation.get("date"))
        for observation in signal.get("observations", [])
        if isinstance(observation, Mapping)
    }
    current = datetime.strptime(str(signal["date"]), "%Y-%m-%d").date() + timedelta(days=1)
    while current <= target_date:
        if calendar.is_trading_day(current) and current.isoformat() not in observation_dates:
            return False
        current += timedelta(days=1)
    return True


def _provenance_for_code(audit: Mapping[str, Any], code: str, target_date: str) -> dict[str, Any]:
    metadata = audit.get("quote_metadata", {}).get(code)
    if not isinstance(metadata, Mapping):
        raise ExactDateEvidenceError(f"EXACT_QUOTE_PROVENANCE_MISSING: {code}")
    return {
        "source_mode": RECOVERY_SOURCE_MODE,
        "provider": metadata.get("provider"),
        "source_identity": metadata.get("source_identity"),
        "provider_version": metadata.get("provider_version"),
        "capture_sha256": metadata.get("capture_sha256"),
        "source_capture_sha256": metadata.get("source_capture_sha256"),
        "capture_path": metadata.get("capture_path"),
        "source_retrieved_at_bjt": metadata.get("source_retrieved_at_bjt"),
        "target_date": target_date,
        "code_git_sha": metadata.get("code_git_sha"),
        "evidence_access": "LOCAL_IMMUTABLE_FILES_ONLY",
    }


def recover_exact_date_review(
    tracker: dict[str, Any],
    *,
    paths: DataPaths | None = None,
    evidence_root: str | Path,
    target_date: date | datetime | str = TARGET_DATE,
    calendar: TradingCalendar | None = None,
    expected_code_git_sha: str = EXPECTED_CODE_GIT_SHA,
) -> dict[str, Any]:
    """Apply the narrow recovery policy and return a bounded audit result."""

    from track_perf import (
        CONFIRMED_ENTRY_UNAVAILABLE,
        PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH,
        REVIEW_POINT_CAPTURED,
        _apply_execution_bar,
        _capture_exact_review_point,
        _ensure_review_points,
        _snapshot_return_pct,
        expected_review_set,
        is_current_prospective_signal,
        verify_review_coverage,
    )

    normalized_date = _date_text(target_date)
    if normalized_date != TARGET_DATE:
        raise ExactDateEvidenceError("EXACT_DATE_RECOVERY_TARGET_DATE_IS_FIXED_TO_2026-09-08")
    cal = calendar or default_calendar()
    resolver = paths or DataPaths.from_env()
    package = _audit_package(resolver, normalized_date)
    watchlists = _load_recovery_watchlists(resolver)
    target_codes = {
        str(candidate["code"])
        for list_date in ("2026-09-03", "2026-09-07")
        for candidate in watchlists[list_date]["candidates"]
    }
    audit = audit_exact_date_evidence(
        evidence_root,
        normalized_date,
        calendar=cal,
        expected_code_git_sha=expected_code_git_sha,
        expected_codes=target_codes,
    )
    if audit["integrity_status"] != "PASS":
        raise ExactDateEvidenceError(
            "EXACT_DATE_EVIDENCE_INTEGRITY_FAILED: " + "; ".join(audit["errors"][:5])
        )
    compatibility = audit_price_compatibility(audit, watchlists, target_date=normalized_date)
    if compatibility["incompatible_codes"]:
        raise ExactDateEvidenceError(
            "RECOVERY_PRICE_BASIS_INCOMPATIBLE: "
            + ",".join(sorted(compatibility["incompatible_codes"]))
        )

    expected_before = expected_review_set(tracker, normalized_date, cal)
    quotes = audit["quotes"]
    compatible_codes = set(compatibility["compatible_codes"])
    execution = {
        "expected": len(watchlists["2026-09-07"]["candidates"]),
        "evidence_found": 0,
        "price_compatible": 0,
        "recovered": 0,
        "missing_codes": [],
        "status_counts": {},
    }
    for candidate in watchlists["2026-09-07"]["candidates"]:
        code = str(candidate["code"])
        signal_id = candidate["signal_id"]
        signal = tracker.get("signals", {}).get(signal_id)
        if code in quotes:
            execution["evidence_found"] += 1
        if code in compatible_codes:
            execution["price_compatible"] += 1
        if not isinstance(signal, dict) or not is_current_prospective_signal(signal):
            execution["missing_codes"].append({"code": code, "reason": "TRACKER_SIGNAL_UNAVAILABLE"})
            continue
        if code not in quotes:
            execution["missing_codes"].append({"code": code, "reason": "EXACT_QUOTE_EVIDENCE_MISSING"})
            continue
        if code not in compatible_codes:
            execution["missing_codes"].append({"code": code, "reason": compatibility["missing_codes"].get(code)})
            continue
        provenance = _provenance_for_code(audit, code, normalized_date)
        _apply_execution_bar(
            signal,
            quotes[code],
            date.fromisoformat(normalized_date),
            cal,
            source_mode=RECOVERY_SOURCE_MODE,
            provenance=provenance,
        )
        execution["recovered"] += 1
        status = str(signal.get("status"))
        execution["status_counts"][status] = execution["status_counts"].get(status, 0) + 1

    snapshot = {
        "expected": len(watchlists["2026-09-03"]["candidates"]),
        "evidence_found": 0,
        "price_compatible": 0,
        "recovered": 0,
        "confirmed_entry_returns": 0,
        "path_fully_verified": 0,
        "missing_codes": [],
    }
    for candidate in watchlists["2026-09-03"]["candidates"]:
        code = str(candidate["code"])
        signal = tracker.get("signals", {}).get(candidate["signal_id"])
        if code in quotes:
            snapshot["evidence_found"] += 1
        if code in compatible_codes:
            snapshot["price_compatible"] += 1
        if not isinstance(signal, dict) or not is_current_prospective_signal(signal):
            snapshot["missing_codes"].append({"code": code, "reason": "TRACKER_SIGNAL_UNAVAILABLE"})
            continue
        if code not in quotes:
            snapshot["missing_codes"].append({"code": code, "reason": "EXACT_QUOTE_EVIDENCE_MISSING"})
            continue
        if code not in compatible_codes:
            snapshot["missing_codes"].append({"code": code, "reason": compatibility["missing_codes"].get(code)})
            continue
        point = _ensure_review_points(signal, cal)["T+3"]
        if point.get("scheduled_date") != normalized_date:
            snapshot["missing_codes"].append({"code": code, "reason": "T_PLUS_3_DATE_MISMATCH"})
            continue
        provenance = _provenance_for_code(audit, code, normalized_date)
        confirmed_entry = bool(signal.get("entry_price") and signal.get("first_trigger_date"))
        if confirmed_entry:
            try:
                confirmed_entry = datetime.strptime(
                    str(signal["first_trigger_date"]), "%Y-%m-%d"
                ).date() <= date.fromisoformat(normalized_date)
            except ValueError:
                confirmed_entry = False
        path_status = signal.get("status") if confirmed_entry and _path_complete(
            signal, date.fromisoformat(normalized_date), cal
        ) else PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH
        reason = None
        if not confirmed_entry:
            reason = CONFIRMED_ENTRY_UNAVAILABLE
        elif path_status == PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH:
            reason = PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH
        changed = _capture_exact_review_point(
            signal,
            "T+3",
            quotes[code],
            cal,
            path_status=path_status,
            reason=reason,
            source_mode=RECOVERY_SOURCE_MODE,
            provenance=provenance,
        )
        if changed or point.get("status") == REVIEW_POINT_CAPTURED:
            snapshot["recovered"] += 1
        if _snapshot_return_pct(signal, quotes[code].get("price")) is not None:
            snapshot["confirmed_entry_returns"] += 1
        if path_status != PATH_UNVERIFIED_MISSING_PRIOR_EXECUTION_PATH:
            snapshot["path_fully_verified"] += 1

    coverage = verify_review_coverage(
        tracker,
        normalized_date,
        expected=expected_before,
        calendar=cal,
    )
    tracker["review_coverage"] = coverage
    tracker["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tracker["recovery_audit"] = {
        "status": "RECOVERY_APPLIED",
        "policy": RECOVERY_SOURCE_MODE,
        "target_date": normalized_date,
        "evidence_root": audit["evidence_root"],
        "integrity_status": audit["integrity_status"],
        "evidence_pair_count": audit["pair_count"],
        "valid_pair_count": audit["valid_pair_count"],
        "unknown_origin_count": audit["unknown_origin_count"],
        "provider_calls": 0,
        "source_access_mode": audit["source_access_mode"],
        "package": package,
        "watchlists": {
            list_date: {
                "count": WATCHLIST_SPECS[list_date]["count"],
                "sha256": WATCHLIST_SPECS[list_date]["sha256"],
            }
            for list_date in WATCHLIST_SPECS
        },
        "price_semantics": compatibility,
        "execution_2026_09_07": execution,
        "snapshot_2026_09_03_t_plus_3": snapshot,
        "review_coverage": coverage,
    }
    return {
        "status": "RECOVERY_APPLIED",
        "policy": RECOVERY_SOURCE_MODE,
        "target_date": normalized_date,
        "evidence_root": audit["evidence_root"],
        "integrity_status": audit["integrity_status"],
        "evidence_pair_count": audit["pair_count"],
        "valid_pair_count": audit["valid_pair_count"],
        "provider_calls": 0,
        "execution_2026_09_07": execution,
        "snapshot_2026_09_03_t_plus_3": snapshot,
        "review_coverage": coverage,
    }
