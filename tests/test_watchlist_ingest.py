import json

import pytest

from data_paths import DataPaths
from test_watchlist_schema import payload as schema_payload


def payload(**overrides):
    return schema_payload(**{"date": "2026-09-03", "strategy_version": "B_BREAKOUT_RETEST_LEGACY_V1_1", **overrides})
from track_perf import ingest, new_tracker
from watchlist_schema import WatchlistIntegrityError


def write_watchlist(paths: DataPaths, date_value: str, **overrides) -> None:
    data = payload(date=date_value, **overrides)
    paths.watchlist_file(date_value).write_text(json.dumps(data), encoding="utf-8")


def test_valid_production_watchlist_is_ingested(tmp_path):
    paths = DataPaths(tmp_path)
    write_watchlist(paths, "2026-09-03")

    tracker = new_tracker()

    assert ingest(tracker, paths=paths) == 1
    assert len(tracker["signals"]) == 1


def test_invalid_canonical_watchlist_is_explicitly_skipped(tmp_path):
    paths = DataPaths(tmp_path)
    write_watchlist(paths, "2026-09-03")
    invalid_path = paths.root / "watchlist_20260904.json"
    invalid_path.write_text(json.dumps(payload(date="2026-09-03")), encoding="utf-8")

    with pytest.warns(RuntimeWarning, match="SKIP_LEGACY_OR_OUT_OF_SCOPE_WATCHLIST"):
        assert ingest(new_tracker(), paths=paths) == 1


def test_isolated_legacy_invalid_watchlist_does_not_block_production_ingest(tmp_path):
    paths = DataPaths(tmp_path)
    write_watchlist(paths, "2026-09-03")
    legacy_dir = paths.root / "legacy_invalid"
    legacy_dir.mkdir()
    (legacy_dir / "watchlist_20260904.json").write_text(
        json.dumps(payload(date="2026-09-03")),
        encoding="utf-8",
    )

    assert paths.watchlist_files() == [paths.watchlist_file("2026-09-03")]
    assert ingest(new_tracker(), paths=paths) == 1
