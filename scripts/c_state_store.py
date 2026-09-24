"""Copy the immutable C research subtree to/from its private recovery repo."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
from typing import Sequence

from c_prospective_capture import C_OUTPUT_ROOT, CaptureError, _safe_output_root


_C_RELATIVE = Path("data/research/c_prospective_capture_v1")
_FORBIDDEN_STATE_SEGMENTS = {
    "runtime-state",
    "runtime_state",
    "reports",
    "watchlist",
    "watchlists",
    "formal",
    "production",
    "validation",
    "final_oos",
    "continuous_speed_probe",
    "shadow_monitor",
}


def _copy_missing(source: Path, target: Path) -> None:
    if target.exists():
        if not target.is_file() or source.read_bytes() != target.read_bytes():
            raise CaptureError("C_STATE_STORE_CONFLICT", f"immutable C state differs at {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, target)
        except FileExistsError:
            if not target.is_file() or source.read_bytes() != target.read_bytes():
                raise CaptureError("C_STATE_STORE_CONFLICT", f"immutable C state differs concurrently at {target}")
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def sync_c_store(state_repo: str | Path, *, direction: str) -> int:
    workspace_root = _safe_output_root()
    state_root = (Path(state_repo).resolve() / _C_RELATIVE).resolve()
    if _FORBIDDEN_STATE_SEGMENTS.intersection(part.lower() for part in state_root.parts):
        raise CaptureError("FORBIDDEN_DIRECTORY_REFUSED", "C state cannot be placed under a production, report, list, runtime, or forbidden path")
    if tuple(part.lower() for part in state_root.parts[-len(_C_RELATIVE.parts):]) != tuple(
        part.lower() for part in _C_RELATIVE.parts
    ):
        raise CaptureError("FORBIDDEN_DIRECTORY_REFUSED", "private state path must end in the independent C research root")
    if direction == "restore":
        source_root, target_root = state_root, workspace_root
    elif direction == "publish":
        source_root, target_root = workspace_root, state_root
    else:
        raise ValueError("direction must be restore or publish")
    if not source_root.exists():
        return 0
    copied = 0
    for source in sorted(source_root.rglob("*")):
        relative = source.relative_to(source_root)
        if relative.parts[0] == ".locks" or source.name.endswith(".tmp"):
            continue
        if source.is_symlink():
            raise CaptureError("C_STATE_STORE_CONFLICT", f"symlinks are not allowed in C state: {source}")
        if not source.is_file():
            continue
        target = target_root / relative
        _copy_missing(source, target)
        copied += 1
    return copied


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("direction", choices=("restore", "publish"))
    parser.add_argument("--state-repo", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(f"C state {args.direction}: {sync_c_store(args.state_repo, direction=args.direction)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
