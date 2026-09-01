"""Cross-machine development preflight and read-only provider capability audit.

This command is intentionally not a generation entry point.  It never creates a
GenerationInputManifest, a live package, a watchlist, or a persisted diagnostic.
Provider probes, when requested, inspect only the current provider snapshot in
memory and report counts/capability summaries.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT_SNAPSHOT_DIAGNOSTIC_LABEL = "LOCAL_CURRENT_SNAPSHOT_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE"
EXPECTED_DISTRIBUTIONS = {
    "pandas": ("pandas", "2.2.3"),
    "requests": ("requests", "2.32.3"),
    "exchange-calendars": ("exchange_calendars", "4.13.2"),
    "pyarrow": ("pyarrow", "17.0.0"),
    "akshare": ("akshare", "1.18.94"),
    "pytest": ("pytest", "8.3.5"),
}


def _status(ok: bool, *, expected: str | None = None, actual: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "PASS" if ok else "FAIL"}
    if expected is not None:
        result["expected"] = expected
    if actual is not None:
        result["actual"] = actual
    return result


def dependency_status() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for distribution, (module, expected) in EXPECTED_DISTRIBUTIONS.items():
        if importlib.util.find_spec(module) is None:
            result[distribution] = _status(False, expected=expected, actual="MISSING")
            continue
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            actual = "MISSING"
        result[distribution] = _status(actual == expected, expected=expected, actual=actual)
    return result


def environment_status() -> dict[str, Any]:
    from data_paths import resolve_data_root

    configured_root = resolve_data_root(project_root=PROJECT_ROOT)
    return {
        "env_vars": {
            "HITHINK_FINANCE_API_KEY": bool(os.environ.get("HITHINK_FINANCE_API_KEY", "").strip()),
            "ASHARE_DATA_ROOT": bool(os.environ.get("ASHARE_DATA_ROOT", "").strip()),
        },
        "data_root": {
            "exists": configured_root.exists(),
            "is_directory": configured_root.is_dir(),
            "readable": os.access(configured_root, os.R_OK),
            "writable": os.access(configured_root, os.W_OK),
        },
    }


def calendar_status() -> dict[str, Any]:
    from trading_calendar import default_calendar

    try:
        calendar = default_calendar()
        session_close = calendar.session_close("2026-09-01")
        timezone_ok = session_close.tzinfo is not None and session_close.tzinfo.utcoffset(session_close) is not None
        return {
            "status": "PASS" if timezone_ok else "FAIL",
            "calendar": "XSHG",
            "timezone": "Asia/Shanghai",
            "session_close_timezone_aware": timezone_ok,
        }
    except Exception as exc:
        return {
            "status": "FAIL",
            "calendar": "XSHG",
            "timezone": "Asia/Shanghai",
            "error_type": type(exc).__name__,
        }


def _frame_rows(frame: Any) -> list[dict[str, Any]]:
    if hasattr(frame, "to_dict"):
        return [dict(row) for row in frame.to_dict(orient="records")]
    if isinstance(frame, (list, tuple)):
        return [dict(row) for row in frame]
    raise TypeError(f"unsupported provider frame: {type(frame).__name__}")


def _provider_code(value: Any) -> str:
    from live_acquisition import _code

    return _code(value, "provider symbol")


def _scoped_universe(rows: list[dict[str, Any]]) -> dict[str, str]:
    symbols: dict[str, str] = {}
    for row in rows:
        exchange = str(row.get("exchange", "")).strip().upper()
        asset_type = str(row.get("asset_type", "")).strip().lower()
        if exchange not in {"SH", "SZ"} or asset_type != "a-share":
            continue
        code = _provider_code(row.get("ticker", row.get("thscode")))
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        if code in symbols:
            raise ValueError(f"duplicate scoped universe symbol: {code}")
        symbols[code] = name
    return dict(sorted(symbols.items()))


def _sector_audit(
    definitions: list[dict[str, Any]],
    members_by_sector: dict[str, list[dict[str, Any]]],
    universe_names: dict[str, str],
) -> dict[str, Any]:
    from live_acquisition import normalize_display_name

    memberships: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    raw_rows = 0
    for definition in definitions:
        sector_code = str(definition["label"])
        for row in members_by_sector[sector_code]:
            symbol = _provider_code(row.get("代码", row.get("code")))
            name = row.get("名称", row.get("name"))
            if not isinstance(name, str):
                raise ValueError(f"missing sector display name for {symbol}")
            memberships[symbol].append(
                {
                    "sector_code": sector_code,
                    "sector_name": definition.get("板块"),
                    "sector_chg": definition.get("涨跌幅"),
                    "display_name": name,
                }
            )
            raw_rows += 1

    exact_duplicate_rows: list[dict[str, Any]] = []
    ambiguous_symbols: list[str] = []
    ambiguous_memberships: list[dict[str, Any]] = []
    unique_sector_symbols: set[str] = set()
    for symbol, records in sorted(memberships.items()):
        unique_keys = {
            (record["sector_code"], record["sector_name"], record["sector_chg"], record["display_name"])
            for record in records
        }
        unique_sector_symbols.add(symbol)
        if len(unique_keys) == 1 and len(records) > 1:
            exact_duplicate_rows.append(
                {
                    "symbol": symbol,
                    "repeated_row_count": len(records),
                    "sector_code": records[0]["sector_code"],
                    "sector_name": records[0]["sector_name"],
                    "sector_chg": records[0]["sector_chg"],
                    "display_name": records[0]["display_name"],
                }
            )
        elif len(unique_keys) > 1:
            ambiguous_symbols.append(symbol)
            ambiguous_memberships.append({"symbol": symbol, "memberships": records})

    common = sorted(set(universe_names) & unique_sector_symbols)
    sector_names = {
        symbol: memberships[symbol][0]["display_name"]
        for symbol in common
    }
    raw_matches = [symbol for symbol in common if universe_names[symbol] == sector_names[symbol]]
    normalized_matches = [
        symbol
        for symbol in common
        if normalize_display_name(universe_names[symbol]) == normalize_display_name(sector_names[symbol])
    ]
    return {
        "raw_member_rows": raw_rows,
        "unique_member_symbols": len(unique_sector_symbols),
        "common_symbols": len(common),
        "exact_raw_name_matches": len(raw_matches),
        "raw_name_mismatches": len(common) - len(raw_matches),
        "normalized_name_matches": len(normalized_matches),
        "normalization_only_mismatches_resolved": len(normalized_matches) - len(raw_matches),
        "universe_symbols_not_in_sector_set": len(set(universe_names) - unique_sector_symbols),
        "sector_symbols_outside_universe": len(unique_sector_symbols - set(universe_names)),
        "repeated_sector_membership_signal_count": sum(item["repeated_row_count"] - 1 for item in exact_duplicate_rows),
        "exact_duplicate_symbols": exact_duplicate_rows,
        "ambiguous_symbols": ambiguous_symbols,
        "ambiguous_memberships": ambiguous_memberships,
    }


def provider_status(*, probe_provider: bool) -> dict[str, Any]:
    import requests

    from live_acquisition import (
        HITHINK_ADJUSTMENT_API,
        HITHINK_BASE_URL,
        HITHINK_INDEX_KLINE_API,
        HITHINK_QUOTE_API,
        HITHINK_STOCK_KLINE_API,
        HiThinkClient,
        SinaSectorClient,
    )

    result: dict[str, Any] = {
        "diagnostic_label": CURRENT_SNAPSHOT_DIAGNOSTIC_LABEL,
        "probe_is_current_snapshot_only": True,
        "formal_package_created": False,
        "hithink": {},
        "exact_sina": {},
    }
    key_present = bool(os.environ.get("HITHINK_FINANCE_API_KEY", "").strip())
    if not key_present:
        result["hithink"] = {"status": "MISSING_CREDENTIAL_PRESENCE"}
    else:
        try:
            client = HiThinkClient()
            report = client.capability_report()
            result["hithink"] = {
                "status": "PASS",
                "api_version": report.get("api_version"),
                "live_primary_status": report.get("live_primary_status"),
                "apis": sorted(report.get("apis", {})),
            }
            if probe_provider:
                universe_rows = client.universe(timeout=15.0)
                universe_names = _scoped_universe(universe_rows)
                result["hithink"]["current_universe_raw_rows"] = len(universe_rows)
                result["hithink"]["current_sh_sz_a_share_symbols"] = len(universe_names)
                sample_symbol = next(iter(universe_names), "600519")
                sample_thscode = f"{sample_symbol}.{'SH' if sample_symbol.startswith('6') else 'SZ'}"
                start_ms = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)
                end_ms = int(datetime(2026, 8, 20, tzinfo=timezone.utc).timestamp() * 1000)
                endpoint_probes: dict[str, Any] = {}
                for label, path, params in (
                    (
                        "snapshot",
                        HITHINK_QUOTE_API,
                        {"thscode": sample_thscode},
                    ),
                    (
                        "adjustment_events",
                        HITHINK_ADJUSTMENT_API,
                        {"thscode": sample_thscode, "to": "2026-08-20"},
                    ),
                ):
                    try:
                        response = requests.get(
                            f"{HITHINK_BASE_URL}{path}",
                            params=params,
                            headers={"X-api-key": os.environ["HITHINK_FINANCE_API_KEY"]},
                            timeout=15,
                        )
                        payload = response.json()
                        endpoint_probes[label] = {
                            "status": "PASS" if response.status_code == 200 and payload.get("code") == 0 else "FAIL",
                            "http_status": response.status_code,
                            "code_zero": payload.get("code") == 0,
                        }
                    except Exception as exc:
                        endpoint_probes[label] = {"status": "FAIL", "error_type": type(exc).__name__}
                try:
                    stock_bars = client.historical_bars(
                        sample_thscode,
                        start=start_ms,
                        end=end_ms,
                        index=False,
                        timeout=15,
                    )
                    endpoint_probes["stock_historical"] = {
                        "status": "PASS" if stock_bars else "FAIL",
                        "bar_count": len(stock_bars),
                    }
                except Exception as exc:
                    endpoint_probes["stock_historical"] = {"status": "FAIL", "error_type": type(exc).__name__}
                try:
                    index_bars = client.historical_bars(
                        "000001.SH",
                        start=start_ms,
                        end=end_ms,
                        index=True,
                        timeout=15,
                    )
                    endpoint_probes["index_historical"] = {
                        "status": "PASS" if index_bars else "FAIL",
                        "bar_count": len(index_bars),
                    }
                except Exception as exc:
                    endpoint_probes["index_historical"] = {"status": "FAIL", "error_type": type(exc).__name__}
                result["hithink"]["endpoint_probes"] = endpoint_probes
        except Exception as exc:
            result["hithink"] = {"status": "FAIL", "error_type": type(exc).__name__}
            universe_names = {}

    try:
        sina = SinaSectorClient()
        report = sina.capability_report()
        result["exact_sina"] = {
            "status": "PASS",
            "package_version": report.get("version"),
            "taxonomy": report.get("taxonomy"),
            "exact_legacy_taxonomy": report.get("exact_legacy_taxonomy"),
            "apis": sorted(report.get("apis", {})),
        }
        if probe_provider:
            definition_rows = _frame_rows(sina.sector_definitions())
            members_by_sector: dict[str, list[dict[str, Any]]] = {}
            for definition in definition_rows:
                sector_code = str(definition["label"])
                members_by_sector[sector_code] = _frame_rows(sina.sector_members(sector_code))
            result["exact_sina"]["current_sector_definitions"] = len(definition_rows)
            result["exact_sina"]["completed_member_calls"] = len(members_by_sector)
            if universe_names:
                result["current_snapshot_sector_audit"] = _sector_audit(
                    definition_rows, members_by_sector, universe_names
                )
    except Exception as exc:
        result["exact_sina"] = {"status": "FAIL", "error_type": type(exc).__name__}
    if not probe_provider:
        result["hithink"]["endpoint_probe"] = "NOT_RUN"
        result["exact_sina"]["endpoint_probe"] = "NOT_RUN"
    return result


def build_report(*, probe_provider: bool) -> dict[str, Any]:
    try:
        ZoneInfo("Asia/Shanghai")
        timezone_status = "PASS"
    except Exception:
        timezone_status = "FAIL"
    return {
        "diagnostic_label": CURRENT_SNAPSHOT_DIAGNOSTIC_LABEL,
        "runtime": {"python": sys.version.split()[0]},
        "dependencies": dependency_status(),
        "environment": environment_status(),
        "timezone": {"Asia/Shanghai": timezone_status},
        "calendar": calendar_status(),
        "providers": provider_status(probe_provider=probe_provider),
        "google_drive": {
            "status": "APP_CONNECTOR_PROBE_REQUIRED",
            "raw_upload_readback": "APP_CONNECTOR_PROBE_REQUIRED",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probe-provider",
        action="store_true",
        help="perform current, in-memory HiThink/Sina capability and coverage probes",
    )
    args = parser.parse_args()
    print(json.dumps(build_report(probe_provider=args.probe_provider), ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
