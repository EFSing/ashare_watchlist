"""Controlled development-candidate generation and artifact lifecycle.

This module connects an already-frozen close-generation input manifest to the
existing research evaluator.  It is intentionally a development harness: it
does not promote the legacy strategy, read Final OOS, or fetch live data.
"""

from __future__ import annotations

import copy
import base64
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
GENERATION_FINGERPRINT_SCHEMA = "DEVELOPMENT_GENERATION_FINGERPRINT_V1"
CANONICAL_WATCHLIST_SCHEMA = "WATCHLIST_SCHEMA_V1"
RUN_SUCCESS = "SUCCESS"
# Compatibility alias for callers that used the original success status.
RUN_PUBLISHED = RUN_SUCCESS
RUN_ALREADY_CURRENT = "OUTPUT_ALREADY_CURRENT"
RUN_NO_CANDIDATES = "NO_CANDIDATES"
# Compatibility alias: zero candidates is now a successful selection outcome.
RUN_NO_QUALIFIED_CANDIDATES = RUN_NO_CANDIDATES
RUN_INPUT_NOT_READY = "INPUT_NOT_READY"
RUN_EVALUATION_FAILURE = "EVALUATION_FAILURE"
RUN_MISSING_DISPLAY_NAME = "MISSING_DISPLAY_NAME"
RUN_OUTPUT_CONFLICT = "OUTPUT_CONFLICT"
RUN_OUTPUT_WRITE_FAILURE = "OUTPUT_WRITE_FAILURE"
MONITOR_HEALTHY = "HEALTHY"
MONITOR_MISSING_OUTPUT = "MISSING_CANONICAL_OUTPUT"
MONITOR_INVALID_OUTPUT = "INVALID_CANONICAL_OUTPUT"
MONITOR_UNTRACKED_OUTPUT = "UNTRACKED_CANONICAL_OUTPUT"
BUY_TYPE = "A 平台突破"
SELECTION_QUALIFIED = "QUALIFIED_CANDIDATES"


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
    generation_fingerprint: str
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
    generation_fingerprint: str | None
    message: str


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _path_identity(value: str) -> str:
    """Shorten only a secondary failure/conflict path component."""

    return value[:16]


def _full_path_identity(value: str) -> str:
    """Encode the complete SHA without truncation or Windows path separators."""

    try:
        return base64.urlsafe_b64encode(bytes.fromhex(value)).decode("ascii").rstrip("=")
    except ValueError:
        raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "generation_fingerprint must be a SHA-256 hex digest")


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


def _display_names_for_symbols(symbols: Any, normalized_names: Mapping[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for symbol in symbols:
        try:
            code = _code(symbol)
        except DevelopmentCandidateError:
            continue
        if code in normalized_names:
            values[code] = normalized_names[code]
    return {code: values[code] for code in sorted(values)}


def _generation_identity(
    manifest: GenerationInputManifest,
    *,
    normalized_names: Mapping[str, str],
    symbols: Any,
    market_env: Mapping[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Return the full output identity and its auditable auxiliary inputs."""

    display_names = _display_names_for_symbols(symbols, normalized_names)
    canonical_market_env = copy.deepcopy(dict(market_env))
    auxiliary_values = {
        "display_names": display_names,
        "market_env": canonical_market_env,
    }
    auxiliary_inputs = {
        "display_names": {
            "identity": "normalized_display_name_mapping",
            "sha256": _sha256_bytes(_canonical_json(display_names)),
            "values": display_names,
        },
        "market_env": {
            "identity": "canonical_market_env_payload",
            "sha256": _sha256_bytes(_canonical_json(canonical_market_env)),
            "values": canonical_market_env,
        },
    }
    payload: dict[str, Any] = {
        "fingerprint_schema": GENERATION_FINGERPRINT_SCHEMA,
        "development_candidate_schema": DEVELOPMENT_CANDIDATE_SCHEMA,
        "canonical_watchlist_schema": CANONICAL_WATCHLIST_SCHEMA,
        "input_fingerprint": manifest.input_fingerprint,
        "strategy_identity": {
            "version": STRATEGY_VERSION,
            "spec_sha256": STRATEGY_SPEC_SHA256,
            "qualification_status": QUALIFIED_LEGACY_BASELINE,
        },
        "buy_type": BUY_TYPE,
        "auxiliary_inputs": auxiliary_values,
    }
    return _sha256_bytes(_canonical_json(payload)), payload, auxiliary_inputs


def _empty_or_normalized_names(names: Mapping[str, str]) -> dict[str, str]:
    try:
        return _normalized_names(names)
    except (AttributeError, DevelopmentCandidateError):
        return {}


class DevelopmentCandidateStore:
    """Versioned development artifacts plus one canonical publish path."""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.lifecycle_root = self.data_root / "development_candidate"

    def canonical_path(self, as_of_date: str) -> Path:
        return self.data_root / f"watchlist_{as_of_date.replace('-', '')}.json"

    def version_path(
        self, as_of_date: str, generation_fingerprint: str, strategy_version: str = STRATEGY_VERSION
    ) -> Path:
        return (
            self.lifecycle_root
            / "versions"
            / _full_path_identity(generation_fingerprint)
            / f"watchlist_{as_of_date.replace('-', '')}.json"
        )

    def run_manifest_path(
        self,
        as_of_date: str,
        generation_fingerprint: str,
        strategy_version: str = STRATEGY_VERSION,
        run_key: str | None = None,
    ) -> Path:
        # The primary artifact identity is the complete generation SHA.  Only
        # the optional secondary key is shortened to keep failure paths safe.
        path_key = _full_path_identity(generation_fingerprint)
        if run_key is not None:
            # Failure/conflict keys can contain another SHA; shorten that
            # component too and retain the full identities in the JSON record.
            path_key = f"{path_key}-{_path_identity(run_key)}"
        return (
            self.lifecycle_root
            / "runs"
            / path_key
            / "run_manifest.json"
        )

    def _write_run_manifest(self, path: Path, record: Mapping[str, Any]) -> None:
        _write_immutable(path, _canonical_json(record))

    def _record(
        self,
        manifest: GenerationInputManifest,
        *,
        generation_fingerprint: str,
        generation_fingerprint_payload: Mapping[str, Any],
        auxiliary_inputs: Mapping[str, Any],
        status: str,
        candidate_count: int,
        evaluation_counts: Mapping[str, int],
        selection_status: str,
        output_sha256: str | None = None,
        failure_message: str | None = None,
        run_key: str | None = None,
    ) -> Path:
        path = self.run_manifest_path(manifest.signal_date, generation_fingerprint, run_key=run_key)
        record: dict[str, Any] = {
            "schema_version": DEVELOPMENT_CANDIDATE_SCHEMA,
            "status": status,
            "selection_status": selection_status,
            "strategy_version": STRATEGY_VERSION,
            "strategy_spec_sha256": STRATEGY_SPEC_SHA256,
            "strategy_identity": {
                "version": STRATEGY_VERSION,
                "spec_sha256": STRATEGY_SPEC_SHA256,
            },
            "as_of_date": manifest.run_context.as_of_date,
            "signal_date": manifest.signal_date,
            "earliest_execution_date": manifest.earliest_execution_date,
            "input_fingerprint": manifest.input_fingerprint,
            "generation_fingerprint": generation_fingerprint,
            "generation_fingerprint_payload": dict(generation_fingerprint_payload),
            "auxiliary_inputs": dict(auxiliary_inputs),
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

    @staticmethod
    def _result(
        status: str,
        manifest: GenerationInputManifest,
        generation_fingerprint: str,
        candidate_count: int,
        output_sha256: str | None,
        output_path: Path | None,
        run_path: Path,
    ) -> DevelopmentRunResult:
        return DevelopmentRunResult(
            status=status,
            as_of_date=manifest.signal_date,
            earliest_execution_date=manifest.earliest_execution_date or "",
            input_fingerprint=manifest.input_fingerprint or "",
            generation_fingerprint=generation_fingerprint,
            strategy_version=STRATEGY_VERSION,
            candidate_count=candidate_count,
            output_sha256=output_sha256,
            output_path=output_path,
            run_manifest_path=run_path,
        )

    def _records(self, as_of_date: str, strategy_version: str) -> list[dict[str, Any]]:
        run_root = self.lifecycle_root / "runs"
        records: list[dict[str, Any]] = []
        for manifest_path in sorted(run_root.glob("*/run_manifest.json")):
            try:
                record = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                isinstance(record, dict)
                and record.get("as_of_date") == as_of_date
                and record.get("strategy_version") == strategy_version
            ):
                records.append(record)
        return records

    @staticmethod
    def _provenance_matches(record: Mapping[str, Any], output_sha256: str) -> bool:
        if record.get("status") != RUN_SUCCESS:
            return False
        generation_payload = record.get("generation_fingerprint_payload")
        generation_fingerprint = record.get("generation_fingerprint")
        if not isinstance(generation_payload, Mapping) or not isinstance(generation_fingerprint, str):
            return False
        if record.get("input_fingerprint") != generation_payload.get("input_fingerprint"):
            return False
        if generation_payload.get("fingerprint_schema") != GENERATION_FINGERPRINT_SCHEMA:
            return False
        if generation_payload.get("development_candidate_schema") != DEVELOPMENT_CANDIDATE_SCHEMA:
            return False
        payload_strategy = generation_payload.get("strategy_identity")
        record_strategy = record.get("strategy_identity")
        if not isinstance(payload_strategy, Mapping) or not isinstance(record_strategy, Mapping):
            return False
        if payload_strategy.get("version") != record.get("strategy_version"):
            return False
        if payload_strategy.get("spec_sha256") != record.get("strategy_spec_sha256"):
            return False
        if record_strategy.get("version") != record.get("strategy_version"):
            return False
        if record_strategy.get("spec_sha256") != record.get("strategy_spec_sha256"):
            return False
        try:
            if _sha256_bytes(_canonical_json(generation_payload)) != generation_fingerprint:
                return False
        except (TypeError, ValueError):
            return False
        payload_auxiliary = generation_payload.get("auxiliary_inputs")
        record_auxiliary = record.get("auxiliary_inputs")
        if not isinstance(payload_auxiliary, Mapping) or not isinstance(record_auxiliary, Mapping):
            return False
        for auxiliary_name in ("display_names", "market_env"):
            payload_values = payload_auxiliary.get(auxiliary_name)
            record_values = record_auxiliary.get(auxiliary_name)
            if not isinstance(record_values, Mapping) or record_values.get("values") != payload_values:
                return False
            try:
                if record_values.get("sha256") != _sha256_bytes(_canonical_json(payload_values)):
                    return False
            except (TypeError, ValueError):
                return False
        output = record.get("output")
        return isinstance(output, Mapping) and output.get("file_sha256") == output_sha256

    def _identity_for_failure(
        self,
        manifest: GenerationInputManifest,
        *,
        names: Mapping[str, str],
        market_env: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        normalized_names = _empty_or_normalized_names(names)
        try:
            symbols = manifest.universe.symbols
        except AttributeError:
            symbols = ()
        return _generation_identity(
            manifest,
            normalized_names=normalized_names,
            symbols=symbols,
            market_env=market_env,
        )

    def generate(
        self,
        manifest: GenerationInputManifest,
        *,
        names: Mapping[str, str],
        market_env: Mapping[str, Any],
    ) -> DevelopmentRunResult:
        """Evaluate and publish one deterministic development candidate.

        A successful evaluator run always publishes a schema-valid canonical
        watchlist, including the legitimate ``candidates=[]`` result.  An
        existing canonical file is never overwritten by ``generate``.
        """

        if not isinstance(manifest, GenerationInputManifest) or manifest.status != READY_FOR_STRATEGY_EVALUATION:
            raise DevelopmentCandidateError(RUN_INPUT_NOT_READY, "manifest is not ready for strategy evaluation")
        if not isinstance(names, Mapping) or not isinstance(market_env, Mapping):
            raise DevelopmentCandidateError(RUN_INPUT_NOT_READY, "names and market_env must be mappings")

        try:
            evaluations = list(evaluate_universe(manifest))
        except Exception as exc:
            generation_fingerprint, generation_payload, auxiliary_inputs = self._identity_for_failure(
                manifest, names=names, market_env=market_env
            )
            run_path = self._record(
                manifest,
                generation_fingerprint=generation_fingerprint,
                generation_fingerprint_payload=generation_payload,
                auxiliary_inputs=auxiliary_inputs,
                status=RUN_EVALUATION_FAILURE,
                selection_status=RUN_EVALUATION_FAILURE,
                candidate_count=0,
                evaluation_counts={},
                failure_message=str(exc),
                run_key=f"failure-{RUN_EVALUATION_FAILURE}",
            )
            return self._result(RUN_EVALUATION_FAILURE, manifest, generation_fingerprint, 0, None, None, run_path)

        evaluation_counts = Counter(item.status for item in evaluations)
        qualified = [item for item in evaluations if item.status == QUALIFIED_LEGACY_BASELINE]

        try:
            normalized_names = _normalized_names(names)
            generation_fingerprint, generation_payload, auxiliary_inputs = _generation_identity(
                manifest,
                normalized_names=normalized_names,
                symbols=[item.symbol for item in qualified],
                market_env=market_env,
            )
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
            generation_fingerprint, generation_payload, auxiliary_inputs = self._identity_for_failure(
                manifest, names=names, market_env=market_env
            )
            run_path = self._record(
                manifest,
                generation_fingerprint=generation_fingerprint,
                generation_fingerprint_payload=generation_payload,
                auxiliary_inputs=auxiliary_inputs,
                status=exc.status,
                selection_status=exc.status,
                candidate_count=0,
                evaluation_counts=evaluation_counts,
                failure_message=str(exc),
                run_key=f"failure-{exc.status}",
            )
            return self._result(exc.status, manifest, generation_fingerprint, 0, None, None, run_path)
        except (TypeError, ValueError, WatchlistSchemaError) as exc:
            generation_fingerprint, generation_payload, auxiliary_inputs = self._identity_for_failure(
                manifest, names=names, market_env=market_env
            )
            run_path = self._record(
                manifest,
                generation_fingerprint=generation_fingerprint,
                generation_fingerprint_payload=generation_payload,
                auxiliary_inputs=auxiliary_inputs,
                status=RUN_EVALUATION_FAILURE,
                selection_status=RUN_EVALUATION_FAILURE,
                candidate_count=0,
                evaluation_counts=evaluation_counts,
                failure_message=str(exc),
                run_key=f"failure-{RUN_EVALUATION_FAILURE}",
            )
            return self._result(RUN_EVALUATION_FAILURE, manifest, generation_fingerprint, 0, None, None, run_path)

        candidate_count = len(candidates)
        selection_status = RUN_NO_CANDIDATES if candidate_count == 0 else SELECTION_QUALIFIED
        output_bytes = _canonical_json(payload)
        output_sha256 = _sha256_bytes(output_bytes)
        version_path = self.version_path(manifest.signal_date, generation_fingerprint)
        canonical_path = self.canonical_path(manifest.signal_date)

        if canonical_path.exists():
            try:
                existing_sha256 = _sha256_bytes(canonical_path.read_bytes())
            except OSError as exc:
                generation_path = self._record(
                    manifest,
                    generation_fingerprint=generation_fingerprint,
                    generation_fingerprint_payload=generation_payload,
                    auxiliary_inputs=auxiliary_inputs,
                    status=RUN_OUTPUT_WRITE_FAILURE,
                    selection_status=RUN_OUTPUT_WRITE_FAILURE,
                    candidate_count=candidate_count,
                    evaluation_counts=evaluation_counts,
                    failure_message=str(exc),
                    run_key=f"failure-{RUN_OUTPUT_WRITE_FAILURE}",
                )
                return self._result(
                    RUN_OUTPUT_WRITE_FAILURE, manifest, generation_fingerprint, candidate_count, None, None, generation_path
                )
            same_generation = any(
                record.get("generation_fingerprint") == generation_fingerprint
                and self._provenance_matches(record, existing_sha256)
                for record in self._records(manifest.signal_date, STRATEGY_VERSION)
            )
            if existing_sha256 != output_sha256 or not same_generation:
                run_path = self._record(
                    manifest,
                    generation_fingerprint=generation_fingerprint,
                    generation_fingerprint_payload=generation_payload,
                    auxiliary_inputs=auxiliary_inputs,
                    status=RUN_OUTPUT_CONFLICT,
                    selection_status=selection_status,
                    candidate_count=candidate_count,
                    evaluation_counts=evaluation_counts,
                    failure_message=f"canonical output already exists with a different generation identity: {canonical_path}",
                    run_key=f"conflict-{output_sha256}",
                )
                return self._result(
                    RUN_OUTPUT_CONFLICT, manifest, generation_fingerprint, candidate_count, None, None, run_path
                )

        already_current = canonical_path.exists()
        try:
            _write_immutable(version_path, output_bytes)
            if not already_current:
                _atomic_write(canonical_path, output_bytes)
            run_path = self._record(
                manifest,
                # The immutable run record always describes a successful
                # generation; OUTPUT_ALREADY_CURRENT is only the call result.
                generation_fingerprint=generation_fingerprint,
                generation_fingerprint_payload=generation_payload,
                auxiliary_inputs=auxiliary_inputs,
                status=RUN_SUCCESS,
                selection_status=selection_status,
                candidate_count=candidate_count,
                evaluation_counts=evaluation_counts,
                output_sha256=output_sha256,
            )
        except DevelopmentCandidateError as exc:
            run_path = self._record(
                manifest,
                generation_fingerprint=generation_fingerprint,
                generation_fingerprint_payload=generation_payload,
                auxiliary_inputs=auxiliary_inputs,
                status=exc.status,
                selection_status=exc.status,
                candidate_count=candidate_count,
                evaluation_counts=evaluation_counts,
                failure_message=str(exc),
                run_key=f"failure-{exc.status}",
            )
            return self._result(exc.status, manifest, generation_fingerprint, candidate_count, None, None, run_path)
        except OSError as exc:
            try:
                run_path = self._record(
                    manifest,
                    generation_fingerprint=generation_fingerprint,
                    generation_fingerprint_payload=generation_payload,
                    auxiliary_inputs=auxiliary_inputs,
                    status=RUN_OUTPUT_WRITE_FAILURE,
                    selection_status=RUN_OUTPUT_WRITE_FAILURE,
                    candidate_count=candidate_count,
                    evaluation_counts=evaluation_counts,
                    failure_message=str(exc),
                    run_key=f"failure-{RUN_OUTPUT_WRITE_FAILURE}",
                )
            except OSError:
                run_path = self.run_manifest_path(
                    manifest.signal_date,
                    generation_fingerprint,
                    run_key=f"failure-{RUN_OUTPUT_WRITE_FAILURE}",
                )
            return self._result(
                RUN_OUTPUT_WRITE_FAILURE, manifest, generation_fingerprint, candidate_count, None, None, run_path
            )

        return self._result(
            RUN_ALREADY_CURRENT if already_current else RUN_PUBLISHED,
            manifest,
            generation_fingerprint,
            candidate_count,
            output_sha256,
            canonical_path,
            run_path,
        )

    def monitor(self, as_of_date: str, strategy_version: str = STRATEGY_VERSION) -> MonitoringResult:
        """Validate canonical output and its complete immutable provenance."""

        path = self.canonical_path(as_of_date)
        if not path.exists():
            return MonitoringResult(MONITOR_MISSING_OUTPUT, as_of_date, None, None, None, f"missing {path}")
        try:
            load_watchlist(path)
        except (OSError, WatchlistSchemaError) as exc:
            return MonitoringResult(MONITOR_INVALID_OUTPUT, as_of_date, None, None, None, str(exc))
        output_sha256 = _sha256_bytes(path.read_bytes())
        for record in self._records(as_of_date, strategy_version):
            if self._provenance_matches(record, output_sha256):
                return MonitoringResult(
                    MONITOR_HEALTHY,
                    as_of_date,
                    output_sha256,
                    record.get("input_fingerprint"),
                    record.get("generation_fingerprint"),
                    "canonical output and complete immutable generation provenance match",
                )
        return MonitoringResult(
            MONITOR_UNTRACKED_OUTPUT,
            as_of_date,
            output_sha256,
            None,
            None,
            "canonical output is valid but has no matching complete generation provenance",
        )

    def rollback(
        self,
        as_of_date: str,
        generation_fingerprint: str,
        strategy_version: str = STRATEGY_VERSION,
    ) -> MonitoringResult:
        """Restore the canonical path from one immutable full-identity version."""

        version_path = self.version_path(as_of_date, generation_fingerprint, strategy_version)
        if not version_path.exists():
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"version artifact not found: {version_path}")
        run_path = self.run_manifest_path(as_of_date, generation_fingerprint, strategy_version)
        if not run_path.exists():
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"run provenance not found: {run_path}")
        try:
            load_watchlist(version_path)
            record = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, WatchlistSchemaError) as exc:
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"version artifact is invalid: {exc}") from exc
        if record.get("generation_fingerprint") != generation_fingerprint:
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "version provenance generation fingerprint mismatch")
        if not self._provenance_matches(record, _sha256_bytes(version_path.read_bytes())):
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "version provenance is incomplete or inconsistent")
        try:
            _atomic_write(self.canonical_path(as_of_date), version_path.read_bytes())
        except OSError as exc:
            raise DevelopmentCandidateError(RUN_OUTPUT_WRITE_FAILURE, str(exc)) from exc
        return self.monitor(as_of_date, strategy_version)


__all__ = [
    "BUY_TYPE",
    "CANONICAL_WATCHLIST_SCHEMA",
    "DEVELOPMENT_CANDIDATE_SCHEMA",
    "GENERATION_FINGERPRINT_SCHEMA",
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
    "RUN_NO_CANDIDATES",
    "RUN_NO_QUALIFIED_CANDIDATES",
    "RUN_OUTPUT_CONFLICT",
    "RUN_OUTPUT_WRITE_FAILURE",
    "RUN_PUBLISHED",
    "RUN_SUCCESS",
    "MonitoringResult",
]
