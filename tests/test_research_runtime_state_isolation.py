"""Exercise both research publishers against one remote and separate Git checkouts."""

from datetime import datetime
from pathlib import Path
import subprocess

import pytest

import b_structure_volume_shadow as shadow
import c_rule_funnel_capture as funnel
import run_c_daily_watchlist
from c_daily_watchlist import publish_report, write_report
from test_b_structure_volume_shadow import _capture as capture_b, _inputs as b_inputs
from test_c_daily_watchlist import _init_c_state_repo
from test_c_rule_funnel_capture import DAY, _inputs as c_inputs


C_PATH = "c-funnel-runtime-state"
B_PATH = "b-shadow-runtime-state"


@pytest.mark.parametrize(("c", "b"), [
    ("commit_failure", "success"),
    ("push_failure", "success"),
    ("success", "commit_failure"),
    ("success", "push_failure"),
    ("disabled", "success"),
    ("success", "disabled"),
    ("success", "success"),
])
def test_research_writers_start_from_remote_and_publish_independently(tmp_path, monkeypatch, c, b):
    c_input_root = tmp_path / "c-inputs"
    c_input_root.mkdir()
    c_result, prepared, _, _, _, _ = c_inputs(c_input_root, monkeypatch)
    b_result, delivery, formal_state = b_inputs(tmp_path, day=DAY)
    observation = c_input_root / "c-input" / prepared["c_result"]["observation"]["record"]
    report = write_report(observation, tmp_path / "c-report")
    published = publish_report(report, formal_state)
    remote = tmp_path / "remote.git"
    _init_c_state_repo(formal_state, remote)
    # The initial remote tree represents completed Formal B and C publication.
    published.update(status="C_DAILY_REPORT_PUBLISHED", package_sha256=report["package_sha256"])

    git = run_c_daily_watchlist._git

    def remote_head():
        return git(remote, "rev-parse", "runtime-state").strip()

    def fresh(name):
        state = tmp_path / name
        git(tmp_path, "clone", "--config", "core.autocrlf=false", "--depth=1",
            "--branch", "runtime-state", remote.as_uri(), str(state))
        assert git(state, "status", "--porcelain") == b""
        assert git(state, "rev-parse", "HEAD").strip() == remote_head()
        return state

    def fail_at_publish(root, command, *args, **kwargs):
        if (root.name, command + "_failure") in {(C_PATH, c), (B_PATH, b)}:
            raise subprocess.CalledProcessError(1, ["git", command, *args])
        return git(root, command, *args, **kwargs)

    def check_readback(state, receipt, status):
        assert receipt["status"] == status
        assert receipt["runtime_state_sha"].encode() == remote_head()
        assert set(git(remote, "diff-tree", "--no-commit-id", "--name-only", "-r",
                       "runtime-state").decode().splitlines()) == set(receipt["paths"])
        for path in receipt["paths"]:
            assert git(remote, "show", f"runtime-state:{path}") == (state / path).read_bytes()

    def capture_c(state, start=DAY):
        return funnel.capture(
            c_result, prepared, published, state_root=state, output_root=tmp_path / "c-output",
            start_date=start, now=datetime.fromisoformat(DAY + "T19:00:00+08:00"),
        )

    monkeypatch.setattr(run_c_daily_watchlist, "_git", fail_at_publish)
    initial = remote_head()
    expected_history = []
    if c != "disabled":
        c_state = fresh(C_PATH)
        c_staged = capture_c(c_state)
        assert all(path.startswith(f"{funnel.RELATIVE_ROOT.as_posix()}/") for path in c_staged["paths"])
        if c == "success":
            check_readback(c_state, funnel.publish(c_state, c_staged), "C_FUNNEL_REMOTE_READBACK_VERIFIED")
            expected_history.append(remote_head())
        else:
            with pytest.raises(subprocess.CalledProcessError):
                funnel.publish(c_state, c_staged)
            assert remote_head() == initial
            staged = git(c_state, "diff", "--cached", "--name-only").decode().splitlines()
            c_head = git(c_state, "rev-parse", "HEAD").strip()
            if c == "commit_failure":
                assert set(staged) == set(c_staged["paths"])
                assert c_head == initial
            else:
                assert not staged
                assert c_head != initial
                assert git(c_state, "rev-parse", "HEAD^").strip() == initial
            (c_state / "local-only").touch()

    if b != "disabled":
        b_state = fresh(B_PATH)
        assert remote_head() == (expected_history[-1] if expected_history else initial)
        assert (b_state / funnel.RELATIVE_ROOT).exists() == (c == "success")
        assert not (b_state / "local-only").exists()
        inputs = (b_result, delivery, b_state)
        b_staged = capture_b(inputs, tmp_path, start=DAY)
        assert all(path.startswith(f"{shadow.RELATIVE_ROOT.as_posix()}/") for path in b_staged["paths"])
        if b == "success":
            check_readback(b_state, shadow.publish(b_state, b_staged), "B_SHADOW_REMOTE_READBACK_VERIFIED")
            expected_history.append(remote_head())
        else:
            with pytest.raises(subprocess.CalledProcessError):
                shadow.publish(b_state, b_staged)
            assert remote_head() == expected_history[-1]
            for path in c_staged["paths"]:
                assert git(remote, "show", f"runtime-state:{path}") == (c_state / path).read_bytes()

    if c == b == "success":
        retry = fresh("same-date-retry")
        with pytest.raises(ValueError, match="IMMUTABILITY_CONFLICT"):
            capture_c(retry, start="2026-11-03")
        with pytest.raises(ValueError, match="IMMUTABILITY_CONFLICT"):
            capture_b((b_result, delivery, retry), tmp_path, start="2026-11-03")
        assert git(retry, "status", "--porcelain") == b""

    history = git(remote, "rev-list", "--reverse", initial.decode() + "..runtime-state").splitlines()
    assert history == expected_history
    assert git(remote, "diff", initial.decode(), "runtime-state", "--", "data", ":(exclude)data/research") == b""


def test_workflow_uses_independent_fail_soft_checkouts_after_delivery():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/daily_t_close.yml").read_text(encoding="utf-8")
    header, *blocks = workflow.split("\n      - name: ")
    steps = dict(block.split("\n", 1) for block in blocks)
    c_checkout = "Checkout clean runtime-state for C funnel capture"
    b_checkout = "Checkout clean runtime-state for B structure-volume Shadow"
    c_record = "Record prospective C rule funnel after delivery and C publication"
    b_record = "Record independent B structure and volume after completed delivery"
    order = list(steps)
    sequence = [
        "Run genuine XSHG T-close production chain", "Deliver production report by Email",
        "Persist delivery receipt to runtime-state", "Enforce production delivery health",
        "Publish bounded C research report after B delivery", c_checkout, c_record, b_checkout, b_record,
    ]
    assert sorted(sequence, key=order.index) == sequence
    assert [line.strip() for line in header.splitlines() if "- cron:" in line] == [
        '- cron: "17 9 * * 1-5"', '- cron: "17 10 * * 1-5"',
    ]
    assert 'python scripts/t_close_runner.py' in steps[sequence[0]]
    assert 'python scripts/run_c_daily_watchlist.py --post-b' in steps[sequence[4]]

    for checkout, recorder, path, step_id in (
        (c_checkout, c_record, C_PATH, "c_funnel_state"),
        (b_checkout, b_record, B_PATH, "b_shadow_state"),
    ):
        assert f"id: {step_id}" in steps[checkout]
        assert "uses: actions/checkout@v4" in steps[checkout]
        assert "ref: runtime-state" in steps[checkout]
        assert "persist-credentials: true" in steps[checkout]
        assert f"path: {path}" in steps[checkout]
        assert f'--state-root "$GITHUB_WORKSPACE/{path}"' in steps[recorder]
        assert '--state-root "$GITHUB_WORKSPACE/runtime-state"' not in steps[recorder]
        assert f"if: always() && steps.{step_id}.outcome == 'success'" in steps[recorder]
        assert all("continue-on-error: true" in steps[name] for name in (checkout, recorder))
    assert C_PATH != B_PATH
    b_gate = next(line for line in steps[b_checkout].splitlines() if "if:" in line)
    assert "if: always()" in b_gate
    assert "steps.c_" not in b_gate and "ENABLE_C_" not in b_gate
    for gate in ("b_production", "b_output_validation", "b_state_push", "b_delivery",
                 "delivery_health", "b_receipt_persist"):
        assert f"steps.{gate}.outcome == 'success'" in b_gate
