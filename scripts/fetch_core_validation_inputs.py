"""Fetch the permitted raw inputs for CORE_SIGNAL_VALIDATION.

This is an acquisition utility, not a performance validator.  It never reads
sector membership, sector score, return, or final-OOS data.  The API key is
read only from ``HITHINK_FINANCE_API_KEY`` and is never printed, serialized,
or included in an exception message.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path


BASE_URL = "https://fuyao.aicubes.cn"
API_KEY_ENV = "HITHINK_FINANCE_API_KEY"
DEFAULT_START = "2016-09-01"
DEFAULT_END = "2026-08-28"


def _utc_midnight_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _api_request(path: str, params: dict[str, str | int] | None = None) -> dict:
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise RuntimeError(f"{API_KEY_ENV} is missing or empty")
    query = urllib.parse.urlencode(params or {})
    url = f"{BASE_URL}{path}{'?' + query if query else ''}"
    request = urllib.request.Request(url, headers={"X-api-key": key})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except Exception as exc:
        raise RuntimeError(f"Financial-API request failed for {path}: {type(exc).__name__}") from exc
    if payload.get("code") != 0:
        raise RuntimeError(f"Financial-API returned nonzero code for {path}: {payload.get('code')}")
    return payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _fetch_index_window(path: Path, start: str, end: str) -> None:
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("code") == 0 and (existing.get("data") or {}).get("item"):
                return
        except (OSError, json.JSONDecodeError):
            pass
    _write_json(
        path,
        _api_request(
            "/api/a-share-index/prices/historical",
            {
                "thscode": "000001.SH",
                "interval": "1d",
                "start": _utc_midnight_ms(start),
                "end": _utc_midnight_ms(end),
            },
        ),
    )


def _download_dump(path: Path, endpoint: str) -> None:
    payload = _api_request(endpoint)
    data = payload.get("data") or {}
    download_url = data.get("presigned_url")
    if not isinstance(download_url, str) or not download_url:
        raise RuntimeError(f"Financial-API dump endpoint did not return a download URL: {endpoint}")
    request = urllib.request.Request(download_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=300) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        temporary.replace(path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def fetch(output_dir: Path, start: str, end: str) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    daily_k = output_dir / "daily_k.parquet"
    adjustment = output_dir / "adjustment_factors.parquet"
    index_files = [
        output_dir / "index_000001_SH_2023.json",
        output_dir / "index_000001_SH_2024.json",
        output_dir / "index_000001_SH_2025.json",
        output_dir / "index_000001_SH_2026.json",
    ]

    if not daily_k.exists():
        _download_dump(daily_k, "/api/dump/market-dumps/daily-k/download-url")
    if not adjustment.exists():
        _download_dump(adjustment, "/api/dump/market-dumps/adjustment-factors/download-url")
    _fetch_index_window(index_files[0], "2023-01-01", "2023-12-31")
    _fetch_index_window(index_files[1], "2024-01-01", "2024-12-31")
    _fetch_index_window(index_files[2], "2025-01-01", "2025-12-31")
    _fetch_index_window(index_files[3], "2026-01-01", end)

    files = {
        "daily_k": [daily_k],
        "adjustment_factors": [adjustment],
        "index": index_files,
    }
    return {
        "source": "HiThink Financial-API",
        "as_of_range": {"start": start, "end": end},
        "files": {
            name: [
                {
                    "path": str(path.as_posix()),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
                for path in paths
            ]
            for name, paths in files.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    args = parser.parse_args()
    result = fetch(args.output_dir, args.start, args.end)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
