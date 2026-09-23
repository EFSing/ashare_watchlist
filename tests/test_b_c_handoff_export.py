from __future__ import annotations

import json
import zipfile

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
    archive = tmp_path / f"b-c-20260827-{persisted.file_sha256}.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in target.rglob("*"):
            if path.is_file():
                bundle.write(path, path.relative_to(target).as_posix())
    download = tmp_path / "independent-download" / archive.name
    download.parent.mkdir()
    download.write_bytes(archive.read_bytes())
    receipt = handoff.verify_download(download, target_date="2026-08-27",
                                      package_sha256=persisted.file_sha256,
                                      repository="private/test", tag="b-c-input-20260827")
    assert receipt["status"] == "HANDOFF_VERIFIED"
    assert receipt["files"] == json.loads((target / "handoff.json").read_bytes())["files"]
    assert receipt["archive_bytes"] == download.stat().st_size
    with pytest.raises(ValueError, match="identity mismatch"):
        handoff.verify_download(download, target_date="2026-08-26",
                                package_sha256=persisted.file_sha256,
                                repository="private/test", tag="b-c-input-20260827")
    damaged = download.parent / "damaged.zip"
    with zipfile.ZipFile(download) as original, zipfile.ZipFile(damaged, "w") as rewritten:
        for name in original.namelist():
            data = original.read(name)
            rewritten.writestr(name, b"corrupt" if name == "package.json" else data)
    with pytest.raises(ValueError, match="SHA or length mismatch"):
        handoff.verify_download(damaged, target_date="2026-08-27",
                                package_sha256=persisted.file_sha256,
                                repository="private/test", tag="b-c-input-20260827")
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
