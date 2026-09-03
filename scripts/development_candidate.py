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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from a_platform_breakout import (
    QUALIFIED_LEGACY_BASELINE,
    STRATEGY_SPEC_SHA256,
    STRATEGY_VERSION,
    CandidateEvaluation,
    evaluate_universe,
)
from b_breakout_retest_v1_1 import (
    STRATEGY_SPEC_SHA256 as B_STRATEGY_SPEC_SHA256,
    STRATEGY_VERSION as B_STRATEGY_VERSION,
    evaluate_universe as evaluate_b_universe,
)
from generation_contract import GenerationInputManifest, READY_FOR_STRATEGY_EVALUATION
from watchlist_schema import WatchlistSchemaError, load_watchlist, validate_watchlist


DEVELOPMENT_CANDIDATE_SCHEMA = "DEVELOPMENT_CANDIDATE_RUN_V1"
GENERATION_FINGERPRINT_SCHEMA = "DEVELOPMENT_GENERATION_FINGERPRINT_V1"
CANONICAL_WATCHLIST_SCHEMA = "WATCHLIST_SCHEMA_V1"
INVALIDATION_SCHEMA = "DEVELOPMENT_CANDIDATE_INVALIDATION_V1"
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
USER_TRADABILITY_ELIGIBILITY_POLICY = "USER_TRADABILITY_ELIGIBILITY_NON_ST_V1"
INELIGIBLE_ST = "INELIGIBLE_ST"


class DevelopmentCandidateError(ValueError):
    """A fail-closed development candidate lifecycle error."""

    def __init__(self, status: str, message: str) -> None:
        self.status = status
        super().__init__(f"{status}: {message}")


@dataclass(frozen=True)
class StrategyBinding:
    """The small strategy dependency bundle used by one generation call."""

    strategy_version: str
    strategy_spec_sha256: str
    qualification_status: str
    buy_type: str
    evaluate_universe: Callable[[GenerationInputManifest], Sequence[CandidateEvaluation]]


A_STRATEGY_BINDING = StrategyBinding(
    strategy_version=STRATEGY_VERSION,
    strategy_spec_sha256=STRATEGY_SPEC_SHA256,
    qualification_status=QUALIFIED_LEGACY_BASELINE,
    buy_type=BUY_TYPE,
    evaluate_universe=evaluate_universe,
)
B_STRATEGY_BINDING = StrategyBinding(
    strategy_version=B_STRATEGY_VERSION,
    strategy_spec_sha256=B_STRATEGY_SPEC_SHA256,
    qualification_status=QUALIFIED_LEGACY_BASELINE,
    buy_type="B \u7a81\u7834\u56de\u8e29",
    evaluate_universe=evaluate_b_universe,
)
INVALIDATED_WRONG_EVALUATOR_A_ON_B_INPUT = "INVALIDATED_WRONG_EVALUATOR_A_ON_B_INPUT"


def _binding_for_call(strategy_binding: StrategyBinding | None) -> StrategyBinding:
    """Resolve one call's binding while preserving the legacy A default."""

    if strategy_binding is None:
        # Keep module-level monkeypatching and historical A callers working.
        return StrategyBinding(
            strategy_version=STRATEGY_VERSION,
            strategy_spec_sha256=STRATEGY_SPEC_SHA256,
            qualification_status=QUALIFIED_LEGACY_BASELINE,
            buy_type=BUY_TYPE,
            evaluate_universe=evaluate_universe,
        )
    if not isinstance(strategy_binding, StrategyBinding):
        raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "strategy binding is invalid")
    return strategy_binding


def _validate_nominated_candidate(
    binding: StrategyBinding,
    input_provenance: Mapping[str, Any] | None,
) -> None:
    """Require an explicitly bound evaluator to match the input nomination."""

    if not isinstance(input_provenance, Mapping):
        raise DevelopmentCandidateError(
            RUN_OUTPUT_CONFLICT,
            "explicit strategy binding requires nominated candidate provenance",
        )
    candidate = input_provenance.get("candidate", input_provenance)
    if not isinstance(candidate, Mapping):
        raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "nominated candidate identity is missing")
    if (
        candidate.get("strategy_version") != binding.strategy_version
        or candidate.get("spec_sha256") != binding.strategy_spec_sha256
    ):
        raise DevelopmentCandidateError(
            RUN_OUTPUT_CONFLICT,
            "nominated candidate identity does not match the explicit strategy binding",
        )


def _validate_evaluations(
    evaluations: Sequence[CandidateEvaluation],
    binding: StrategyBinding,
) -> None:
    """Reject an evaluator whose output provenance belongs to another strategy."""

    for evaluation in evaluations:
        if not isinstance(evaluation, CandidateEvaluation):
            raise DevelopmentCandidateError(RUN_EVALUATION_FAILURE, "evaluator returned an invalid evaluation")
        if evaluation.strategy_version != binding.strategy_version:
            raise DevelopmentCandidateError(
                RUN_OUTPUT_CONFLICT,
                f"evaluator output strategy mismatch: {evaluation.strategy_version!r}",
            )
        provenance = evaluation.provenance
        if not isinstance(provenance, Mapping):
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "evaluator output provenance is missing")
        if (
            provenance.get("strategy_version") != binding.strategy_version
            or provenance.get("spec_sha256") != binding.strategy_spec_sha256
        ):
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "evaluator output spec provenance mismatch")


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
    b_raw_qualified_count: int | None = None
    st_excluded_count: int | None = None
    final_non_st_qualified_count: int | None = None
    st_excluded: tuple[dict[str, str], ...] = field(default_factory=tuple)


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


def _has_st_marker(name: str) -> bool:
    """Apply the exact user rule: trim, then case-insensitive prefix detection."""

    normalized = name.strip().casefold()
    return normalized.startswith("*st") or normalized.startswith("st")


def apply_user_tradability_eligibility(
    qualified: Sequence[CandidateEvaluation],
    names: Mapping[str, str],
) -> tuple[tuple[CandidateEvaluation, ...], dict[str, Any]]:
    """Filter only final user eligibility after evaluator qualification.

    The evaluator results are not changed. The returned report is the audit
    boundary between raw strategy qualification and the user-facing list.
    """

    normalized_names = _normalized_names(names)
    final_non_st: list[CandidateEvaluation] = []
    excluded: list[dict[str, str]] = []
    for evaluation in qualified:
        code = _code(evaluation.symbol)
        name = normalized_names.get(code)
        if name is None:
            raise DevelopmentCandidateError(RUN_MISSING_DISPLAY_NAME, f"no display name for {evaluation.symbol}")
        if _has_st_marker(name):
            excluded.append({"symbol": code, "name": name, "status": INELIGIBLE_ST})
        else:
            final_non_st.append(evaluation)
    excluded.sort(key=lambda item: item["symbol"])
    report = {
        "policy": USER_TRADABILITY_ELIGIBILITY_POLICY,
        "normalization": "trim + case-insensitive ST marker detection",
        "markers": ["*ST", "ST"],
        "b_raw_qualified_count": len(qualified),
        "st_excluded_count": len(excluded),
        "final_non_st_qualified_count": len(final_non_st),
        "st_excluded": excluded,
    }
    return tuple(final_non_st), report


def _candidate_payload(
    evaluation: CandidateEvaluation,
    names: Mapping[str, str],
    binding: StrategyBinding,
) -> dict[str, Any]:
    if evaluation.status != binding.qualification_status or evaluation.features is None:
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
        "buy_type": binding.buy_type,
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
        "strategy_version": binding.strategy_version,
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
    binding: StrategyBinding,
    normalized_names: Mapping[str, str],
    symbols: Any,
    market_env: Mapping[str, Any],
    user_tradability_eligibility: Mapping[str, Any] | None = None,
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
    if user_tradability_eligibility is not None:
        eligibility = copy.deepcopy(dict(user_tradability_eligibility))
        auxiliary_values["user_tradability_eligibility"] = eligibility
        auxiliary_inputs["user_tradability_eligibility"] = {
            "identity": USER_TRADABILITY_ELIGIBILITY_POLICY,
            "sha256": _sha256_bytes(_canonical_json(eligibility)),
            "values": eligibility,
        }
    payload: dict[str, Any] = {
        "fingerprint_schema": GENERATION_FINGERPRINT_SCHEMA,
        "development_candidate_schema": DEVELOPMENT_CANDIDATE_SCHEMA,
        "canonical_watchlist_schema": CANONICAL_WATCHLIST_SCHEMA,
        "input_fingerprint": manifest.input_fingerprint,
        "strategy_identity": {
            "version": binding.strategy_version,
            "spec_sha256": binding.strategy_spec_sha256,
            "qualification_status": binding.qualification_status,
        },
        "buy_type": binding.buy_type,
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
        binding: StrategyBinding,
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
            "strategy_version": binding.strategy_version,
            "strategy_spec_sha256": binding.strategy_spec_sha256,
            "strategy_identity": {
                "version": binding.strategy_version,
                "spec_sha256": binding.strategy_spec_sha256,
                "qualification_status": binding.qualification_status,
            },
            "buy_type": binding.buy_type,
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
        eligibility = auxiliary_inputs.get("user_tradability_eligibility")
        if isinstance(eligibility, Mapping) and isinstance(eligibility.get("values"), Mapping):
            audit = copy.deepcopy(dict(eligibility["values"]))
            record["user_tradability_eligibility"] = audit
            for field_name in (
                "b_raw_qualified_count",
                "st_excluded_count",
                "final_non_st_qualified_count",
                "st_excluded",
            ):
                record[field_name] = copy.deepcopy(audit.get(field_name))
        self._write_run_manifest(path, record)
        return path

    @staticmethod
    def _result(
        status: str,
        manifest: GenerationInputManifest,
        generation_fingerprint: str,
        binding: StrategyBinding,
        candidate_count: int,
        output_sha256: str | None,
        output_path: Path | None,
        run_path: Path,
        eligibility_report: Mapping[str, Any] | None = None,
    ) -> DevelopmentRunResult:
        report = eligibility_report if isinstance(eligibility_report, Mapping) else {}
        excluded = report.get("st_excluded", ())
        return DevelopmentRunResult(
            status=status,
            as_of_date=manifest.signal_date,
            earliest_execution_date=manifest.earliest_execution_date or "",
            input_fingerprint=manifest.input_fingerprint or "",
            generation_fingerprint=generation_fingerprint,
            strategy_version=binding.strategy_version,
            candidate_count=candidate_count,
            output_sha256=output_sha256,
            output_path=output_path,
            run_manifest_path=run_path,
            b_raw_qualified_count=report.get("b_raw_qualified_count"),
            st_excluded_count=report.get("st_excluded_count"),
            final_non_st_qualified_count=report.get("final_non_st_qualified_count"),
            st_excluded=tuple(copy.deepcopy(item) for item in excluded)
            if isinstance(excluded, (list, tuple))
            else (),
        )

    def _records(self, as_of_date: str, binding: StrategyBinding) -> list[dict[str, Any]]:
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
                and record.get("strategy_version") == binding.strategy_version
            ):
                records.append(record)
        return records

    @staticmethod
    def _provenance_matches(
        record: Mapping[str, Any],
        output_sha256: str,
        binding: StrategyBinding,
    ) -> bool:
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
        if payload_strategy.get("version") != binding.strategy_version:
            return False
        if payload_strategy.get("spec_sha256") != binding.strategy_spec_sha256:
            return False
        if payload_strategy.get("qualification_status") != binding.qualification_status:
            return False
        if generation_payload.get("buy_type") != binding.buy_type:
            return False
        if record.get("strategy_version") != binding.strategy_version:
            return False
        if record.get("strategy_spec_sha256") != binding.strategy_spec_sha256:
            return False
        if record_strategy.get("version") != binding.strategy_version:
            return False
        if record_strategy.get("spec_sha256") != binding.strategy_spec_sha256:
            return False
        if record_strategy.get("qualification_status") != binding.qualification_status:
            return False
        if record.get("buy_type") != binding.buy_type:
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
        if "user_tradability_eligibility" in payload_auxiliary:
            payload_values = payload_auxiliary.get("user_tradability_eligibility")
            record_values = record_auxiliary.get("user_tradability_eligibility")
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
        binding: StrategyBinding,
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
            binding=binding,
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
        strategy_binding: StrategyBinding | None = None,
        input_provenance: Mapping[str, Any] | None = None,
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

        binding = _binding_for_call(strategy_binding)
        try:
            if strategy_binding is not None:
                _validate_nominated_candidate(binding, input_provenance)
            evaluations = list(binding.evaluate_universe(manifest))
            _validate_evaluations(evaluations, binding)
        except DevelopmentCandidateError as exc:
            generation_fingerprint, generation_payload, auxiliary_inputs = self._identity_for_failure(
                manifest, binding=binding, names=names, market_env=market_env
            )
            run_path = self._record(
                manifest,
                binding=binding,
                generation_fingerprint=generation_fingerprint,
                generation_fingerprint_payload=generation_payload,
                auxiliary_inputs=auxiliary_inputs,
                status=exc.status,
                selection_status=exc.status,
                candidate_count=0,
                evaluation_counts={},
                failure_message=str(exc),
                run_key=f"failure-{exc.status}",
            )
            return self._result(exc.status, manifest, generation_fingerprint, binding, 0, None, None, run_path)
        except Exception as exc:
            generation_fingerprint, generation_payload, auxiliary_inputs = self._identity_for_failure(
                manifest, binding=binding, names=names, market_env=market_env
            )
            run_path = self._record(
                manifest,
                binding=binding,
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
            return self._result(
                RUN_EVALUATION_FAILURE, manifest, generation_fingerprint, binding, 0, None, None, run_path
            )

        evaluation_counts = Counter(item.status for item in evaluations)
        qualified = [item for item in evaluations if item.status == binding.qualification_status]

        try:
            normalized_names = _normalized_names(names)
            final_qualified, eligibility_report = apply_user_tradability_eligibility(qualified, normalized_names)
            generation_fingerprint, generation_payload, auxiliary_inputs = _generation_identity(
                manifest,
                binding=binding,
                normalized_names=normalized_names,
                symbols=[item.symbol for item in final_qualified],
                market_env=market_env,
                user_tradability_eligibility=eligibility_report,
            )
            candidates = [_candidate_payload(item, normalized_names, binding) for item in final_qualified]
            candidates.sort(key=lambda item: item["code"])
            if len({item["code"] for item in candidates}) != len(candidates):
                raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "multiple symbols collapse to one A-share code")
            payload = validate_watchlist(
                {
                    "date": manifest.signal_date,
                    "mode": manifest.run_context.mode,
                    "market_env": copy.deepcopy(dict(market_env)),
                    "sectors": _sector_payload(list(final_qualified)),
                    "candidates": candidates,
                    "strategy_version": binding.strategy_version,
                }
            )
        except DevelopmentCandidateError as exc:
            generation_fingerprint, generation_payload, auxiliary_inputs = self._identity_for_failure(
                manifest, binding=binding, names=names, market_env=market_env
            )
            run_path = self._record(
                manifest,
                binding=binding,
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
            return self._result(exc.status, manifest, generation_fingerprint, binding, 0, None, None, run_path)
        except (TypeError, ValueError, WatchlistSchemaError) as exc:
            generation_fingerprint, generation_payload, auxiliary_inputs = self._identity_for_failure(
                manifest, binding=binding, names=names, market_env=market_env
            )
            run_path = self._record(
                manifest,
                binding=binding,
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
            return self._result(
                RUN_EVALUATION_FAILURE, manifest, generation_fingerprint, binding, 0, None, None, run_path
            )

        candidate_count = len(candidates)
        selection_status = RUN_NO_CANDIDATES if candidate_count == 0 else SELECTION_QUALIFIED
        output_bytes = _canonical_json(payload)
        output_sha256 = _sha256_bytes(output_bytes)
        version_path = self.version_path(manifest.signal_date, generation_fingerprint, binding.strategy_version)
        canonical_path = self.canonical_path(manifest.signal_date)

        if canonical_path.exists():
            try:
                existing_sha256 = _sha256_bytes(canonical_path.read_bytes())
            except OSError as exc:
                generation_path = self._record(
                    manifest,
                    binding=binding,
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
                    RUN_OUTPUT_WRITE_FAILURE,
                    manifest,
                    generation_fingerprint,
                    binding,
                    candidate_count,
                    None,
                    None,
                    generation_path,
                )
            same_generation = any(
                record.get("generation_fingerprint") == generation_fingerprint
                and self._provenance_matches(record, existing_sha256, binding)
                for record in self._records(manifest.signal_date, binding)
            )
            if existing_sha256 != output_sha256 or not same_generation:
                run_path = self._record(
                    manifest,
                    binding=binding,
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
                    RUN_OUTPUT_CONFLICT,
                    manifest,
                    generation_fingerprint,
                    binding,
                    candidate_count,
                    None,
                    None,
                    run_path,
                )

        already_current = canonical_path.exists()
        try:
            _write_immutable(version_path, output_bytes)
            if not already_current:
                _atomic_write(canonical_path, output_bytes)
            run_path = self._record(
                manifest,
                binding=binding,
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
                binding=binding,
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
            return self._result(
                exc.status, manifest, generation_fingerprint, binding, candidate_count, None, None, run_path
            )
        except OSError as exc:
            try:
                run_path = self._record(
                    manifest,
                    binding=binding,
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
                    binding.strategy_version,
                    run_key=f"failure-{RUN_OUTPUT_WRITE_FAILURE}",
                )
            return self._result(
                RUN_OUTPUT_WRITE_FAILURE,
                manifest,
                generation_fingerprint,
                binding,
                candidate_count,
                None,
                None,
                run_path,
            )

        return self._result(
            RUN_ALREADY_CURRENT if already_current else RUN_PUBLISHED,
            manifest,
            generation_fingerprint,
            binding,
            candidate_count,
            output_sha256,
            canonical_path,
            run_path,
            eligibility_report,
        )

    def supersede_invalid_canonical(
        self,
        as_of_date: str,
        *,
        expected_sha256: str,
        expected_strategy_version: str,
        formal_run_id: str,
        invalidation_reason: str,
        superseded_at: str,
        correcting_code_sha: str,
        replacement_strategy_version: str,
        replacement_strategy_spec_sha256: str,
    ) -> Path:
        """Retain and invalidate one known-wrong canonical output exactly once."""

        canonical_path = self.canonical_path(as_of_date)
        invalidated_root = self.lifecycle_root / "invalidated" / f"{canonical_path.stem}-{expected_sha256}"
        original_path = invalidated_root / canonical_path.name
        record_path = invalidated_root / "invalidation.json"
        run_path = self.lifecycle_root / "runs" / formal_run_id / "run_manifest.json"

        if canonical_path.exists():
            try:
                original_bytes = canonical_path.read_bytes()
                payload = load_watchlist(canonical_path)
            except (OSError, WatchlistSchemaError) as exc:
                raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"canonical evidence is invalid: {exc}") from exc
            if _sha256_bytes(original_bytes) != expected_sha256:
                raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "canonical SHA does not match expected wrong output")
            if payload.get("strategy_version") != expected_strategy_version:
                raise DevelopmentCandidateError(
                    RUN_OUTPUT_CONFLICT, "canonical strategy identity does not match expected wrong output"
                )
        else:
            if not original_path.exists() or not record_path.exists():
                raise DevelopmentCandidateError(
                    RUN_OUTPUT_CONFLICT, "expected wrong canonical is missing and no complete invalidation evidence exists"
                )
            original_bytes = original_path.read_bytes()
            if _sha256_bytes(original_bytes) != expected_sha256:
                raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "retained canonical evidence SHA mismatch")
            try:
                existing_record = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"invalidation record is invalid: {exc}") from exc
            if not isinstance(existing_record, Mapping) or existing_record.get("status") != INVALIDATED_WRONG_EVALUATOR_A_ON_B_INPUT:
                raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "invalidation record status mismatch")
            return record_path

        if not run_path.exists():
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"formal run manifest not found: {run_path}")
        try:
            run_bytes = run_path.read_bytes()
            run_record = json.loads(run_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"formal run manifest is invalid: {exc}") from exc
        if not isinstance(run_record, Mapping):
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "formal run manifest is not an object")
        run_output = run_record.get("output")
        if (
            run_record.get("status") != RUN_SUCCESS
            or run_record.get("strategy_version") != expected_strategy_version
            or not isinstance(run_output, Mapping)
            or run_output.get("file_sha256") != expected_sha256
            or run_record.get("as_of_date") != as_of_date
        ):
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "formal run does not link to expected wrong output")

        _write_immutable(original_path, original_bytes)
        record: dict[str, Any] = {
            "schema_version": INVALIDATION_SCHEMA,
            "status": INVALIDATED_WRONG_EVALUATOR_A_ON_B_INPUT,
            "reason": invalidation_reason,
            "superseded_at": superseded_at,
            "correcting_code_sha": correcting_code_sha,
            "original": {
                "canonical_logical_path": f"data/{canonical_path.name}",
                "file_sha256": expected_sha256,
                "strategy_version": expected_strategy_version,
                "formal_run_id": formal_run_id,
                "run_manifest_logical_path": f"data/development_candidate/runs/{formal_run_id}/run_manifest.json",
                "run_manifest_file_sha256": _sha256_bytes(run_bytes),
            },
            "retained_evidence": {
                "path": str(original_path),
                "file_sha256": _sha256_bytes(original_bytes),
            },
            "replacement": {
                "canonical_logical_path": f"data/{canonical_path.name}",
                "strategy_version": replacement_strategy_version,
                "strategy_spec_sha256": replacement_strategy_spec_sha256,
            },
        }
        _write_immutable(record_path, _canonical_json(record))
        try:
            canonical_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise DevelopmentCandidateError(RUN_OUTPUT_WRITE_FAILURE, str(exc)) from exc
        return record_path

    def monitor(
        self,
        as_of_date: str,
        strategy_version: str = STRATEGY_VERSION,
        *,
        strategy_binding: StrategyBinding | None = None,
    ) -> MonitoringResult:
        """Validate canonical output and its complete immutable provenance."""

        if strategy_binding is None and strategy_version == B_STRATEGY_VERSION:
            binding = B_STRATEGY_BINDING
        else:
            binding = _binding_for_call(strategy_binding)
        path = self.canonical_path(as_of_date)
        if not path.exists():
            return MonitoringResult(MONITOR_MISSING_OUTPUT, as_of_date, None, None, None, f"missing {path}")
        try:
            load_watchlist(path)
        except (OSError, WatchlistSchemaError) as exc:
            return MonitoringResult(MONITOR_INVALID_OUTPUT, as_of_date, None, None, None, str(exc))
        output_sha256 = _sha256_bytes(path.read_bytes())
        for record in self._records(as_of_date, binding):
            if self._provenance_matches(record, output_sha256, binding):
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
        *,
        strategy_binding: StrategyBinding | None = None,
    ) -> MonitoringResult:
        """Restore the canonical path from one immutable full-identity version."""

        if strategy_binding is None and strategy_version == B_STRATEGY_VERSION:
            binding = B_STRATEGY_BINDING
        else:
            binding = _binding_for_call(strategy_binding)
        version_path = self.version_path(as_of_date, generation_fingerprint, binding.strategy_version)
        if not version_path.exists():
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"version artifact not found: {version_path}")
        run_path = self.run_manifest_path(as_of_date, generation_fingerprint, binding.strategy_version)
        if not run_path.exists():
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"run provenance not found: {run_path}")
        try:
            load_watchlist(version_path)
            record = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, WatchlistSchemaError) as exc:
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, f"version artifact is invalid: {exc}") from exc
        if record.get("generation_fingerprint") != generation_fingerprint:
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "version provenance generation fingerprint mismatch")
        if not self._provenance_matches(record, _sha256_bytes(version_path.read_bytes()), binding):
            raise DevelopmentCandidateError(RUN_OUTPUT_CONFLICT, "version provenance is incomplete or inconsistent")
        try:
            _atomic_write(self.canonical_path(as_of_date), version_path.read_bytes())
        except OSError as exc:
            raise DevelopmentCandidateError(RUN_OUTPUT_WRITE_FAILURE, str(exc)) from exc
        return self.monitor(as_of_date, strategy_binding=binding)


__all__ = [
    "BUY_TYPE",
    "A_STRATEGY_BINDING",
    "B_STRATEGY_BINDING",
    "CANONICAL_WATCHLIST_SCHEMA",
    "DEVELOPMENT_CANDIDATE_SCHEMA",
    "GENERATION_FINGERPRINT_SCHEMA",
    "INVALIDATED_WRONG_EVALUATOR_A_ON_B_INPUT",
    "INVALIDATION_SCHEMA",
    "INELIGIBLE_ST",
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
    "StrategyBinding",
    "USER_TRADABILITY_ELIGIBILITY_POLICY",
    "apply_user_tradability_eligibility",
    "MonitoringResult",
]
