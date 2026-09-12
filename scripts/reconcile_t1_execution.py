#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""Reconcile stored tracker observations with the deterministic T+1 model.

This command is intentionally local and provider-free.  It first prints a
read-only audit; pass --apply only after reviewing that audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from data_paths import DataPaths
from track_perf import (
    build_execution_reconciliation_audit,
    current_prospective_tracker,
    load_tracker,
    reconcile_tracker_execution,
    save_tracker,
)
from trading_calendar import default_calendar


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return Path(tempfile.gettempdir()) / f"perf_tracker_before_t1_execution_reconcile_{stamp}.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="strict report as-of date, YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--apply", action="store_true", help="write the audited replay into perf_tracker.json")
    parser.add_argument("--backup-path", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = DataPaths(args.data_root) if args.data_root else DataPaths.from_env()
    tracker_path = paths.perf_tracker_file()
    try:
        tracker = load_tracker(tracker_path)
        # Validate that retained current-prospective identities still match
        # canonical watchlists before any operational write.
        current_prospective_tracker(tracker, paths)
        calendar = default_calendar()
        audit = build_execution_reconciliation_audit(tracker, args.date, calendar)
        print(json.dumps({"mode": "DRY_AUDIT", **audit}, ensure_ascii=False, sort_keys=True))
        if not args.apply:
            return 0

        before_sha = _sha256(tracker_path)
        backup = (args.backup_path or _default_backup(tracker_path)).expanduser().resolve()
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tracker_path, backup)
        result = reconcile_tracker_execution(tracker, args.date, calendar)
        save_tracker(tracker, tracker_path)
        print(json.dumps({
            "mode": "APPLIED",
            "before_sha256": before_sha,
            "backup_path": str(backup),
            "after_sha256": _sha256(tracker_path),
            "provider_calls": 0,
            **result,
        }, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({
            "mode": "FAILED",
            "error_type": type(exc).__name__,
            "error_detail": str(exc)[:1000],
            "provider_calls": 0,
        }, ensure_ascii=False, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
