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


def test_hithink_raw_response_records_actual_request_window(tmp_path):
    class Response:
        content = b'{"code":0,"data":{"item":[]}}'

        def json(self):
            return json.loads(self.content)

    store = live.TCloseEvidenceStore(tmp_path, "2026-09-22",
                                     actual_retrieved_at_bjt="2026-09-22T17:17:00+08:00")
    client = live.HiThinkClient(api_key="test", request_get=lambda *args, **kwargs: Response(),
                               capture_store=store)
    assert client._read("universe", live.HITHINK_UNIVERSE_API, {"offset": 0}, timeout=1) == {"item": []}
    response = store.latest("hithink_response")
    assert response is not None
    metadata = json.loads(response.metadata_path.read_bytes())
    assert metadata["requested_at_bjt"] <= metadata["received_at_bjt"]
    assert metadata["requested_at_bjt"] != store.actual_retrieved_at_bjt
    assert metadata["file_sha256"] == __import__("hashlib").sha256(response.payload).hexdigest()


def test_same_day_retry_uses_distinct_package_identity(tmp_path):
    evidence = tmp_path / "evidence"
    package = _acquire(evidence_root=evidence,
                       hithink_client=FakeHiThink(bars=_bars(count=120), index_bars=_bars(count=120)),
                       stock_bar_count=120)
    first = live.persist_live_input_package(package, tmp_path / "first")
    altered = json.loads(first.path.read_bytes())
    altered["provenance"]["retry_note"] = "second-run"
    altered.pop("content_sha256")
    altered["content_sha256"] = handoff._sha(handoff._canonical(altered))
    second_path = tmp_path / "second" / "package.json"
    second_path.parent.mkdir()
    second_path.write_bytes(handoff._canonical(altered))
    second_sha = handoff._sha(second_path.read_bytes())
    destination = tmp_path / "private"
    for number, path, sha in ((1, first.path, first.file_sha256), (2, second_path, second_sha)):
        result = tmp_path / f"result-{number}.json"
        result.write_text(json.dumps({
            "status": "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED",
            "as_of_date": "2026-08-27", "input_package": {"path": str(path), "file_sha256": sha},
        }), encoding="utf-8")
        handoff.export(result, evidence, destination)
    assert first.file_sha256 != second_sha
    assert (destination / "20260827" / first.file_sha256 / "package.json").read_bytes() == first.path.read_bytes()
    assert (destination / "20260827" / second_sha / "package.json").read_bytes() == second_path.read_bytes()
