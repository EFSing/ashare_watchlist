from __future__ import annotations

import json

import pytest

import b_c_handoff_export as handoff
import live_acquisition as live
from test_live_acquisition import FakeHiThink, _acquire, _bars


def test_export_exact_b_bytes_and_reject_corrupt_raw(tmp_path):
    evidence = tmp_path / "evidence"
    package = _acquire(evidence_root=evidence,
                       hithink_client=FakeHiThink(bars=_bars(count=120), index_bars=_bars(count=120)),
                       stock_bar_count=120)
    persisted = live.persist_live_input_package(package, tmp_path / "b")
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps({
        "status": "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED",
        "as_of_date": "2026-08-27",
        "input_package": {"path": str(persisted.path), "file_sha256": persisted.file_sha256},
    }), encoding="utf-8")
    exported = handoff.export(result_path, evidence, tmp_path / "private")
    target = tmp_path / "private" / "20260827" / persisted.file_sha256
    assert exported["status"] == "EXPORTED_LOCAL_UNVERIFIED_REMOTE"
    assert (target / "package.json").read_bytes() == persisted.path.read_bytes()
    assert handoff.export(result_path, evidence, tmp_path / "private") == exported
    capture = package.provenance["evidence_capture"]["captures"][0]
    stem = __import__("hashlib").sha256(capture["logical_component_identity"].encode()).hexdigest()
    raw = evidence / "20260827" / capture["component"] / f"{stem}.raw"
    raw.write_bytes(b"damaged")
    with pytest.raises(ValueError, match="raw evidence SHA"):
        handoff.export(result_path, evidence, tmp_path / "private")


def test_failed_b_run_cannot_create_handoff(tmp_path):
    result_path = tmp_path / "failed.json"
    result_path.write_text('{"status":"NO_VALID_INPUT"}', encoding="utf-8")
    destination = tmp_path / "private"
    with pytest.raises(ValueError, match="B success result"):
        handoff.export(result_path, tmp_path / "evidence", destination)
    assert not destination.exists()
