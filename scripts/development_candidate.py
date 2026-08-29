"""Controlled development-candidate generation and artifact lifecycle.

This module connects an already-frozen close-generation input manifest to the
existing research evaluator.  It is intentionally a development harness: it
does not promote the legacy strategy, read Final OOS, or fetch live data.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from a_platform_breakout import (
    QUALIFIED_LEGACY_BASELINE,
    STRATEGY_SPEC_SHA256,
    STRATEGY_VERSION,
    CandidateEvaluation,
    evaluate_universe,
)
from generation_contract import GenerationInputManifest, READY_FOR_STRATEGY_EVALUATION
from watchlist_schema import WatchlistSchemaError, load_watchlist, validate_watchlist


DEVELOPMENT_CANDIDATE_SCHEMA = "DEVELOPMENT_CANDIDATE_RUN_V1"
RUN_PUBLISHED = "PUBLISHED"
RUN_ALREADY_CURRENT = "OUTPUT_ALREADY_CURRENT"
RUN_NO_QUALIFIED_CANDIDATES = "NO_QUALIFIED_CANDIDATES"
RUN_INPUT_NOT_READY = "INPUT_NOT_READY"
RUN_EVALUATION_FAILURE = "EVALUATION_FAILURE"
RUN_MISSING_DISPLAY_NAME = "MISSING_DISPLAY_NAME"
RUN_OUTPUT_CONFLICT = "OUTPUT_CONFLICT"
MONITOR_HEALTHY = "HEALTHY"
MONITOR_MISSING_OUTPUT = "MISSING_CANONICAL_OUTPUT"
MONITOR_INVALID_OUTPUT = "INVALID_CANONICAL_OUTPUT"
MONITOR_UNTRACKED_OUTPUT = "UNTRACKED_CANONICAL_OUTPUT"
BUY_TYPE = "A 平台突破"


class DevelopmentCandidateError(ValueError):
    """A fail-closed development candidate lifecycle error."""

    def __init__(self, status: str, message: str) -> None:
        self.status = status
        super().__init__(f"{status}: {message}")


@dataclass(frozen=True)
class DevelopmentRunResult:
    status: str
    as_of_date: str
    earliest_execution_date: str
    input_fingerprint: str
    strategy_version: str
    candidate_count: int
    output_sha256: str | None
    output_path: Path | None
    run_manifest_path: Path


@dataclass(frozen=True)
class MonitoringResult:
    status: str
    as_of_date: str
    output_sha256: str | None
    input_fingerprint: str | None
    message: str


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _path_identity(value: str) -> str:
    """Keep Windows artifact paths short; the full SHA remains in manifests."""

    return value[:16]


def _finite(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise DevelopmentCandidateError(RUN_EVALUATION_FAILURE, f"{field_name} must be finite")
    return float(value)


def _code(symbol: str) -> str:
    text = str(symbol).strip().lower()
    if text[:2] in {"sh", "sz", "bj"}:
        text = text[2:]
    if len(text) != 6 or not text.isdigit():
        raise DevelopmentCandidateError(RUN_EVALUATION_FAILURE, f"symbol is not a six-digit A-share code: {symbol!r}")
    return text


def _normalized_names(names: Mapping[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for symbol, name in names.items():
        key = str(symbol).strip().lower()
        if key[:2] in {"sh", "sz", "bj"}:
            key = key[2:]
        if not isinstance(name, str) or not name.strip():
            raise DevelopmentCandidateError(RUN_MISSING_DISPLAY_NAME, f"display name is empty for {symbol!r}")
        normalized[key] = name.strip()
    return normalized


def _candidate_payload(evaluation: CandidateEvaluation, names: Mapping[str, str]) -> dict[str, Any]:
    if evaluation.status != QUALIFIED_LEGACY_BASELINE or evaluation.features is None:
        raise DevelopmentCandidateError(RUN_EVALUATION_FAILURE, f"{evaluation.symbol} is not qualified")
    features = evaluation.features
    code = _code(evaluation.symbol)
    name = names.get(code)
    if name is None:
        raise DevelopmentCandidateError(RUN_MISSING_DISPLAY_NAME, f"no display name for {evaluation.symbol}")
    values = {
        "code": code,
        "name": name,
        "sector": features.sector_name,
        "buy_type": BUY_TYPE,
        "score": evaluation.score_total,
        "price": features.close,
        "chg": features.chg1,
        "trigger": evaluation.trigger,
        "support": evaluation.support,
        "stop": evaluation.stop,
        "target": evaluation.target,
        "rr": evaluation.rr,
        "stop_dist": None if evaluation.risk is None else evaluation.risk * 100.0,
        "vol_ratio": features.vol_ratio_k,
        "turnover": features.turnover,
        "target_type": evaluation.target_type,
        "risk": evaluation.risk,
        "setup": evaluation.setup_id,
        "strategy_version": evaluation.strategy_version,
    }
    for field_name, value in values.items():
        if field_name not in {"code", "name", "sector", "buy_type", "target_type", "setup", "strategy_version"}:
            if value is None:
                raise DevelopmentCandidateError(RUN_EVALUATION_FAILURE, f"qualified {code} has no {field_name}")
            _finite(value, f"candidate.{field_name}")
    return values


def _sector_payload(evaluations: list[CandidateEvaluation]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for evaluation in evaluations:
        assert evaluation.features is not None
        features = evaluation.features
        rows[features.sector_name] = {
            "name": features.sector_name,
            "rank": features.sector_rank,
            "chg": features.sector_chg,
        }
    return [rows[name] for name in sorted(rows)]


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _write_immutable(path: Path, content: bytes) -> None:
    if path.exists():
        existing = path.read_bytes()
        if existing != content:
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"immutable artifact differs: {path}")
        return
    _atomic_write(path, content)


class DevelopmentCandidateStore:
    """Versioned development artifacts plus one canonical publish path."""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.lifecycle_root = self.data_root / "development_candidate"

    def canonical_path(self, as_of_date: str) -> Path:
        return self.data_root / f"watchlist_{as_of_date.replace('-', '')}.json"

    def version_path(self, as_of_date: str, input_fingerprint: str, strategy_version: str = STRATEGY_VERSION) -> Path:
        return (
            self.lifecycle_root
            / "versions"
            / strategy_version
            / as_of_date
            / _path_identity(input_fingerprint)
            / f"watchlist_{as_of_date.replace('-', '')}.json"
        )

    def run_manifest_path(
        self,
        as_of_date: str,
        input_fingerprint: str,
        strategy_version: str = STRATEGY_VERSION,
        run_key: str | None = None,
    ) -> Path:
        path_key = _path_identity(input_fingerprint)
        if run_key is not None:
            # Failure/conflict keys can contain another SHA; shorten that
            # component too and retain the full identities in the JSON record.
            path_key = f"{path_key}-{_path_identity(run_key)}"
        return (
            self.lifecycle_root
            / "runs"
            / strategy_version
            / as_of_date
            / path_key
            / "run_manifest.json"
        )

    def _write_run_manifest(self, path: Path, record: Mapping[str, Any]) -> None:
        _write_immutable(path, _canonical_json(record))

    def _record(
        self,
        manifest: GenerationInputManifest,
        *,
        status: str,
        candidate_count: int,
        evaluation_counts: Mapping[str, int],
        output_sha256: str | None = None,
        failure_message: str | None = None,
        run_key: str | None = None,
    ) -> Path:
        input_fingerprint = manifest.input_fingerprint or ""
        path = self.run_manifest_path(manifest.signal_date, input_fingerprint, run_key=run_key)
        record: dict[str, Any] = {
            "schema_version": DEVELOPMENT_CANDIDATE_SCHEMA,
            "status": status,
            "strategy_version": STRATEGY_VERSION,
            "strategy_spec_sha256": STRATEGY_SPEC_SHA256,
            "as_of_date": manifest.run_context.as_of_date,
            "signal_date": manifest.signal_date,
            "earliest_execution_date": manifest.earliest_execution_date,
            "input_fingerprint": manifest.input_fingerprint,
            "input_manifest": manifest.to_dict(),
            "evaluation_counts": dict(sorted(evaluation_counts.items())),
            "candidate_count": candidate_count,
        }
        if output_sha256 is not None:
            record["output"] = {
                "logical_identity": f"watchlist_{manifest.signal_date.replace('-', '')}.json",
                "file_sha256": output_sha256,
            }
        if failure_message is not None:
            record["failure_message"] = failure_message
        self._write_run_manifest(path, record)
        return path

    def generate(
        self,
        manifest: GenerationInputManifest,
        *,
        names: Mapping[str, str],
        market_env: Mapping[str, Any],
    ) -> DevelopmentRunResult:
        """Evaluate and publish one deterministic development candidate.

        No canonical watchlist is written for an input failure, evaluator
        failure, missing display name, or zero qualified candidates.  An
        existing canonical file is never overwritten by ``generate``.
        """

        if not isinstance(manifest, GenerationInputManifest) or manifest.status != READY_FOR_STRATEGY_EVALUATION:
            raise DevelopmentCandidateError(RUN_INPUT_NOT_READY, "manifest is not ready for strategy evaluation")
        if not isinstance(market_env, Mapping):
            raise DevelopmentCandidateError(RUN_INPUT_NOT_READY, "market_env must be a mapping")

        try:
            evaluations = list(evaluate_universe(manifest))
        except Exception as exc:
            run_path = self._record(
                manifest,
                status=RUN_EVALUATION_FAILURE,
                candidate_count=0,
                evaluation_counts={},
                failure_message=str(exc),
                run_key=f"failure-{RUN_EVALUATION_FAILURE}",
            )
            return DevelopmentRunResult(
                RUN_EVALUATION_FAILURE,
                manifest.signal_date,
                manifest.earliest_execution_date or "",
                manifest.input_fingerprint or "",
                STRATEGY_VERSION,
                0,
                None,
                None,
                run_path,
            )

        evaluation_counts = Counter(item.status for item in evaluations)
        qualified = [item for item in evaluations if item.status == QUALIFIED_LEGACY_BASELINE]
        if not qualified:
            run_path = self._record(
                manifest,
                status=RUN_NO_QUALIFIED_CANDIDATES,
                candidate_count=0,
                evaluation_counts=evaluation_counts,
                failure_message="no candidate passed the existing legacy hard gates",
                run_key=f"failure-{RUN_NO_QUALIFIED_CANDIDATES}",
            )
            return DevelopmentRunResult(
                RUN_NO_QUALIFIED_CANDIDATES,
                manifest.signal_date,
                manifest.earliest_execution_date or "",
                manifest.input_fingerprint or "",
                STRATEGY_VERSION,
                0,
                None,
                None,
                run_path,
            )

        try:
            normalized_names = _normalized_names(names)
            candidates = [_candidate_payload(item, normalized_names) for item in qualified]
            candidates.sort(key=lambda item: item["code"])
            if len({item["code"] for item in candidates}) != len(candidates):
                raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "multiple symbols collapse to one A-share code")
            payload = validate_watchlist(
                {
                    "date": manifest.signal_date,
                    "mode": manifest.run_context.mode,
                    "market_env": copy.deepcopy(dict(market_env)),
                    "sectors": _sector_payload(qualified),
                    "candidates": candidates,
                    "strategy_version": STRATEGY_VERSION,
                }
            )
        except DevelopmentCandidateError as exc:
            run_path = self._record(
                manifest,
                status=exc.status,
                candidate_count=0,
                evaluation_counts=evaluation_counts,
                failure_message=str(exc),
                run_key=f"failure-{exc.status}",
            )
            return DevelopmentRunResult(
                exc.status,
                manifest.signal_date,
                manifest.earliest_execution_date or "",
                manifest.input_fingerprint or "",
                STRATEGY_VERSION,
                0,
                None,
                None,
                run_path,
            )
        except (TypeError, ValueError, WatchlistSchemaError) as exc:
            run_path = self._record(
                manifest,
                status=RUN_EVALUATION_FAILURE,
                candidate_count=0,
                evaluation_counts=evaluation_counts,
                failure_message=str(exc),
                run_key=f"failure-{RUN_EVALUATION_FAILURE}",
            )
            return DevelopmentRunResult(
                RUN_EVALUATION_FAILURE,
                manifest.signal_date,
                manifest.earliest_execution_date or "",
                manifest.input_fingerprint or "",
                STRATEGY_VERSION,
                0,
                None,
                None,
                run_path,
            )

        output_bytes = _canonical_json(payload)
        output_sha256 = _sha256_bytes(output_bytes)
        input_fingerprint = manifest.input_fingerprint or ""
        version_path = self.version_path(manifest.signal_date, input_fingerprint)
        canonical_path = self.canonical_path(manifest.signal_date)

        if canonical_path.exists() and canonical_path.read_bytes() != output_bytes:
            run_path = self._record(
                manifest,
                status=RUN_OUTPUT_CONFLICT,
                candidate_count=len(candidates),
                evaluation_counts=evaluation_counts,
                failure_message=f"canonical output already exists with a different identity: {canonical_path}",
                run_key=f"conflict-{_sha256_bytes(output_bytes)}",
            )
            return DevelopmentRunResult(
                RUN_OUTPUT_CONFLICT,
                manifest.signal_date,
                manifest.earliest_execution_date or "",
                input_fingerprint,
                STRATEGY_VERSION,
                len(candidates),
                None,
                None,
                run_path,
            )

        try:
            _write_immutable(version_path, output_bytes)
            already_current = canonical_path.exists()
            if not already_current:
                _atomic_write(canonical_path, output_bytes)
            run_path = self._record(
                manifest,
                # The immutable run record describes the successful version;
                # OUTPUT_ALREADY_CURRENT is only the idempotent call result.
                status=RUN_PUBLISHED,
                candidate_count=len(candidates),
                evaluation_counts=evaluation_counts,
                output_sha256=output_sha256,
            )
        except DevelopmentCandidateError as exc:
            run_path = self._record(
                manifest,
                status=exc.status,
                candidate_count=len(candidates),
                evaluation_counts=evaluation_counts,
                failure_message=str(exc),
                run_key=f"failure-{exc.status}",
            )
            return DevelopmentRunResult(
                exc.status,
                manifest.signal_date,
                manifest.earliest_execution_date or "",
                input_fingerprint,
                STRATEGY_VERSION,
                len(candidates),
                None,
                None,
                run_path,
            )

        return DevelopmentRunResult(
            RUN_ALREADY_CURRENT if already_current else RUN_PUBLISHED,
            manifest.signal_date,
            manifest.earliest_execution_date or "",
            input_fingerprint,
            STRATEGY_VERSION,
            len(candidates),
            output_sha256,
            canonical_path,
            run_path,
        )

    def monitor(self, as_of_date: str, strategy_version: str = STRATEGY_VERSION) -> MonitoringResult:
        """Validate canonical output and its immutable run provenance."""

        path = self.canonical_path(as_of_date)
        if not path.exists():
            return MonitoringResult(MONITOR_MISSING_OUTPUT, as_of_date, None, None, f"missing {path}")
        try:
            load_watchlist(path)
        except (OSError, WatchlistSchemaError) as exc:
            return MonitoringResult(MONITOR_INVALID_OUTPUT, as_of_date, None, None, str(exc))
        output_sha256 = _sha256_bytes(path.read_bytes())
        run_root = self.lifecycle_root / "runs" / strategy_version / as_of_date
        for manifest_path in sorted(run_root.glob("*/run_manifest.json")):
            try:
                record = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            output = record.get("output", {})
            if output.get("file_sha256") == output_sha256:
                return MonitoringResult(
                    MONITOR_HEALTHY,
                    as_of_date,
                    output_sha256,
                    record.get("input_fingerprint"),
                    "canonical output and immutable run provenance match",
                )
        return MonitoringResult(
            MONITOR_UNTRACKED_OUTPUT,
            as_of_date,
            output_sha256,
            None,
            "canonical output is valid but has no matching immutable run provenance",
        )

    def rollback(
        self,
        as_of_date: str,
        input_fingerprint: str,
        strategy_version: str = STRATEGY_VERSION,
    ) -> MonitoringResult:
        """Restore the canonical path from one immutable version artifact."""

        version_path = self.version_path(as_of_date, input_fingerprint, strategy_version)
        if not version_path.exists():
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"version artifact not found: {version_path}")
        run_path = self.run_manifest_path(as_of_date, input_fingerprint, strategy_version)
        if not run_path.exists():
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"run provenance not found: {run_path}")
        try:
            load_watchlist(version_path)
            record = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, WatchlistSchemaError) as exc:
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"version artifact is invalid: {exc}") from exc
        if record.get("input_fingerprint") != input_fingerprint:
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "version provenance fingerprint mismatch")
        output = record.get("output", {})
        version_sha256 = _sha256_bytes(version_path.read_bytes())
        if output.get("file_sha256") != version_sha256:
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "version provenance output hash mismatch")
        _atomic_write(self.canonical_path(as_of_date), version_path.read_bytes())
        return self.monitor(as_of_date, strategy_version)


__all__ = [
    "BUY_TYPE",
    "DEVELOPMENT_CANDIDATE_SCHEMA",
    "DevelopmentCandidateError",
    "DevelopmentCandidateStore",
    "DevelopmentRunResult",
    "MONITOR_HEALTHY",
    "MONITOR_INVALID_OUTPUT",
    "MONITOR_MISSING_OUTPUT",
    "MONITOR_UNTRACKED_OUTPUT",
    "RUN_ALREADY_CURRENT",
    "RUN_EVALUATION_FAILURE",
    "RUN_INPUT_NOT_READY",
    "RUN_MISSING_DISPLAY_NAME",
    "RUN_NO_QUALIFIED_CANDIDATES",
    "RUN_OUTPUT_CONFLICT",
    "RUN_PUBLISHED",
    "MonitoringResult",
]
