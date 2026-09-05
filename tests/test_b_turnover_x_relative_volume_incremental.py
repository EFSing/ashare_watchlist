from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from b_turnover_x_relative_volume_incremental import (
    DATE_FIELD,
    TURNOVER_FIELD,
    _canonical_turnover_rows,
    _acquisition_targets,
    _load_qualified_identity_without_outcomes,
    _raw_payload_from_frame,
    _relative_volume,
)


def test_bounded_targets_retry_failed_before_pending():
    symbols = ["000001.sz", "000002.sz", "000003.sz", "000004.sz"]
    checkpoint = {
        "completed": {"000003.sz": {"status": "COMPLETED"}},
        "failed": {"000002.sz": {"status": "FAILED"}},
    }
    assert _acquisition_targets(symbols, checkpoint, 2) == ["000002.sz", "000001.sz"]


def test_identity_extraction_does_not_require_outcome_values():
    path = Path(__file__).with_name("_turnover_identity_test_events.jsonl.gz")
    raw = b'{"outcomes":{"5D":{"return_pct":999}},"symbol":"000001.sz","signal_date":"2023-06-30","setup_id":"B_BREAKOUT_RETEST"}\n'
    try:
        with path.open("wb") as raw_handle:
            with gzip.GzipFile(fileobj=raw_handle, mode="wb", filename="", mtime=0) as handle:
                handle.write(raw)
        assert _load_qualified_identity_without_outcomes(path) == {
            ("000001.sz", "2023-06-30", "B_BREAKOUT_RETEST")
        }
    finally:
        path.unlink(missing_ok=True)


def test_canonical_turnover_rows_deduplicate_exact_duplicates():
    payload = {"rows": [
        {DATE_FIELD: "2023-06-30", TURNOVER_FIELD: 1.25},
        {DATE_FIELD: "2023-06-30", TURNOVER_FIELD: 1.25},
        {DATE_FIELD: "2023-07-03", TURNOVER_FIELD: 2.5},
    ]}
    rows, meta = _canonical_turnover_rows(payload, "000001.sz")
    assert rows == [
        {"symbol": "000001.sz", "date": "2023-06-30", "turnover_rate_pct": 1.25},
        {"symbol": "000001.sz", "date": "2023-07-03", "turnover_rate_pct": 2.5},
    ]
    assert meta["duplicate_rows_deduplicated"] == 1


def test_conflicting_duplicate_values_fail_closed():
    payload = {"rows": [
        {DATE_FIELD: "2023-06-30", TURNOVER_FIELD: 1.25},
        {DATE_FIELD: "2023-06-30", TURNOVER_FIELD: 1.26},
    ]}
    with pytest.raises(RuntimeError, match="conflicting duplicate"):
        _canonical_turnover_rows(payload, "000001.sz")


def test_raw_payload_preserves_provider_field_identity():
    import pandas as pd

    frame = pd.DataFrame([{DATE_FIELD: "2023-06-30", TURNOVER_FIELD: 1.25}])
    payload = _raw_payload_from_frame("000001.sz", frame)
    assert payload["provider_function"] == "ak.stock_zh_a_hist"
    assert payload["parameters"]["period"] == "daily"
    assert payload["parameters"]["adjust"] == ""
    assert TURNOVER_FIELD in payload["raw_columns"]


def test_relative_volume_excludes_t_from_the_twenty_bar_baseline():
    volume = [100.0] * 21
    volume[-1] = 250.0
    assert _relative_volume(volume) == (2.5, None)
    volume[-2] = 500.0
    assert _relative_volume(volume) == (250.0 / ((1900.0 + 500.0) / 20.0), None)
