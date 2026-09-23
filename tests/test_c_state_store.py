from __future__ import annotations

from pathlib import Path

import pytest

import c_prospective_capture as capture
from c_prospective_capture import CaptureError
from c_state_store import sync_c_store


def _c_root(parent: Path) -> Path:
    return parent / "data" / "research" / "c_prospective_capture_v1"


def test_private_state_store_roundtrips_only_immutable_c_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first_root = _c_root(tmp_path / "device-a")
    monkeypatch.setattr(capture, "C_OUTPUT_ROOT", first_root)
    artifact = first_root / "manifests" / "20260922" / "capture.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b'{"namespace":"C_PROSPECTIVE_CAPTURE_V1"}\n')
    private_repo = tmp_path / "private-c-state"
    assert sync_c_store(private_repo, direction="publish") == 1

    second_root = _c_root(tmp_path / "device-b")
    monkeypatch.setattr(capture, "C_OUTPUT_ROOT", second_root)
    assert sync_c_store(private_repo, direction="restore") == 1
    assert (second_root / artifact.relative_to(first_root)).read_bytes() == artifact.read_bytes()


def test_private_state_store_refuses_conflicting_immutable_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _c_root(tmp_path / "device-a")
    monkeypatch.setattr(capture, "C_OUTPUT_ROOT", root)
    relative = Path("logs/20260922/attempt.json")
    target = root / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"first")
    private_repo = tmp_path / "private-c-state"
    sync_c_store(private_repo, direction="publish")
    target.write_bytes(b"changed")
    with pytest.raises(CaptureError, match="C_STATE_STORE_CONFLICT"):
        sync_c_store(private_repo, direction="publish")


def test_private_state_store_rejects_runtime_state_destination(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _c_root(tmp_path / "device-a")
    monkeypatch.setattr(capture, "C_OUTPUT_ROOT", root)
    with pytest.raises(CaptureError, match="FORBIDDEN_DIRECTORY_REFUSED"):
        sync_c_store(tmp_path / "runtime-state", direction="publish")
    assert not (tmp_path / "runtime-state").exists()
