from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import t_close_runner as runner


def test_runner_persists_input_package_before_generating_watchlist(monkeypatch, tmp_path):
    events = []
    package = SimpleNamespace(
        generation_input_manifest=SimpleNamespace(signal_date="2026-08-27"),
        display_names={"600519": "测试股份"},
        market_env={"as_of_date": "2026-08-27"},
        provenance={"evidence_capture": {"status": "T_CLOSE_VOLATILE_EVIDENCE_SECURED"}},
    )
    persisted = SimpleNamespace(
        status="PERSISTED",
        path=tmp_path / "input.json",
        file_sha256="a" * 64,
    )
    candidate = SimpleNamespace(
        status=runner.RUN_SUCCESS,
        output_path=tmp_path / "watchlist.json",
        output_sha256="b" * 64,
        candidate_count=1,
        run_manifest_path=tmp_path / "run_manifest.json",
    )

    def fake_acquire(*args, **kwargs):
        events.append("acquire")
        assert kwargs["evidence_root"] == tmp_path / "evidence"
        return package

    def fake_persist(value, output_root):
        events.append("persist_package")
        assert value is package
        assert output_root == tmp_path
        return persisted

    class FakeStore:
        def __init__(self, output_root):
            assert output_root == tmp_path

        def generate(self, manifest, *, names, market_env):
            events.append("generate_watchlist")
            assert manifest is package.generation_input_manifest
            assert names == package.display_names
            assert market_env == package.market_env
            assert events == ["acquire", "persist_package", "generate_watchlist"]
            return candidate

    monkeypatch.setattr(runner, "acquire_live_generation_inputs", fake_acquire)
    monkeypatch.setattr(runner, "persist_live_input_package", fake_persist)
    monkeypatch.setattr(runner, "DevelopmentCandidateStore", FakeStore)
    monkeypatch.setattr(runner, "_git_sha", lambda: "c" * 40)

    result = runner.run("2026-08-27", tmp_path, tmp_path / "evidence")

    assert result["status"] == "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED"
    assert result["input_package"]["path"] == str(persisted.path)
    assert result["watchlist"]["path"] == str(candidate.output_path)
    assert events == ["acquire", "persist_package", "generate_watchlist"]
