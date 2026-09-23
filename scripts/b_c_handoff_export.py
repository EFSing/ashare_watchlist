"""Export B's already-frozen input bytes for a separate, private C handoff.

This command only reads B artifacts. Its destination must be persisted by an
independent operator; writing a runner-local directory is not a completed handoff.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _copy_immutable(data: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != data:
            raise ValueError(f"immutable handoff conflict: {destination}")
        return
    fd, name = tempfile.mkstemp(dir=destination.parent, prefix=".handoff-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(name, destination)
        except FileExistsError:
            if destination.read_bytes() != data:
                raise ValueError(f"immutable handoff conflict: {destination}")
    finally:
        Path(name).unlink(missing_ok=True)


def export(result_path: Path, evidence_root: Path, destination_root: Path) -> dict[str, object]:
    result = json.loads(result_path.read_bytes())
    if result.get("status") != "T_CLOSE_EVIDENCE_PACKAGE_AND_WATCHLIST_PERSISTED":
        raise ValueError("B success result is required")
    source = result.get("input_package") or {}
    package_path = Path(source["path"])
    package_bytes = package_path.read_bytes()
    package_sha = _sha(package_bytes)
    if package_sha != source.get("file_sha256"):
        raise ValueError("B package file SHA mismatch")
    package = json.loads(package_bytes)
    content = dict(package)
    declared = content.pop("content_sha256", None)
    if declared != _sha(_canonical(content)):
        raise ValueError("B package internal content SHA mismatch")
    day = package["generation_input_manifest"]["signal_date"]
    if day != result.get("as_of_date"):
        raise ValueError("B result and package T differ")
    captures = (package.get("provenance", {}).get("evidence_capture") or {}).get("captures")
    if not isinstance(captures, list) or not captures:
        raise ValueError("B raw evidence capture is unavailable")
    target = destination_root / day.replace("-", "") / package_sha
    if (target.resolve().is_relative_to(package_path.parent.resolve())
            or target.resolve().is_relative_to(evidence_root.resolve())):
        raise ValueError("handoff destination must be independent of B inputs")
    files: list[dict[str, object]] = []
    for capture in captures:
        if capture.get("completeness_status") != "COMPLETE":
            raise ValueError("B evidence capture is incomplete")
        component, logical = capture["component"], capture["logical_component_identity"]
        if not isinstance(component, str) or not component or Path(component).name != component:
            raise ValueError("invalid B capture component")
        stem = hashlib.sha256(logical.encode("utf-8")).hexdigest()
        relative = Path(day.replace("-", "")) / component / stem
        for suffix in (".raw", ".json"):
            source_path = evidence_root / relative.with_suffix(suffix)
            data = source_path.read_bytes()
            if suffix == ".raw":
                if _sha(data) != capture["file_sha256"] or len(data) != capture["byte_length"]:
                    raise ValueError("B raw evidence SHA or length mismatch")
            else:
                sidecar = json.loads(data)
                if (sidecar.get("file_sha256") != capture["file_sha256"]
                        or sidecar.get("logical_component_identity") != logical
                        or sidecar.get("byte_length") != capture["byte_length"]):
                    raise ValueError("B raw sidecar mismatch")
            output = Path("evidence") / relative.with_suffix(suffix)
            files.append({"path": output.as_posix(), "sha256": _sha(data), "bytes": len(data)})
            _copy_immutable(data, target / output)
    _copy_immutable(package_bytes, target / "package.json")
    marker = target / "handoff.json"
    if marker.exists():
        previous = json.loads(marker.read_bytes())
        if (previous.get("package_sha256") != package_sha
                or previous.get("files") != [{"path": "package.json", "sha256": package_sha,
                                               "bytes": len(package_bytes)}, *files]):
            raise ValueError("immutable handoff manifest conflict")
        return {"status": previous["status"], "path": str(target), "package_sha256": package_sha,
                "file_count": len(previous["files"])}
    manifest = {
        "schema_version": "B_C_READONLY_HANDOFF_V1", "status": "EXPORTED_LOCAL_UNVERIFIED_REMOTE",
        "target_date": day, "exported_at_bjt": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "package_sha256": package_sha, "content_sha256": declared,
        "input_coverage": package["provenance"]["input_coverage"],
        "files": [{"path": "package.json", "sha256": package_sha, "bytes": len(package_bytes)}, *files],
    }
    _copy_immutable(_canonical(manifest), marker)
    return {"status": manifest["status"], "path": str(target), "package_sha256": package_sha,
            "file_count": len(manifest["files"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b-result", type=Path, required=True)
    parser.add_argument("--b-evidence-root", type=Path, required=True)
    parser.add_argument("--private-destination", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.b_result, args.b_evidence_root, args.private_destination)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
