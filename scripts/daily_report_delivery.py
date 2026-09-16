"""Deliver the canonical daily close report through Email and Bark.

This module is intentionally small and provider-neutral.  Market-data
acquisition and canonical runtime-state persistence happen outside it.  The
production workflow calls this module only after the first runtime-state
commit has succeeded; the module then records an operational delivery receipt
for bounded retry/idempotency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import smtplib
import ssl
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from watchlist_schema import INPUT_COVERAGE_DEGRADED, validate_input_coverage

_BJT = timezone(timedelta(hours=8))
DEFAULT_BARK_SERVER_URL = "https://api.day.app"
RECEIPT_SCHEMA_VERSION = "DAILY_REPORT_DELIVERY_RECEIPT_V1"
FAILURE_NOTICE_SCHEMA_VERSION = "DAILY_FAILURE_NOTICE_V1"
DELIVERY_SUCCESS = "DELIVERY_SUCCESS"
DELIVERY_DEGRADED = "DELIVERY_DEGRADED"
DELIVERY_FAILED = "DELIVERY_FAILED"
ALREADY_DELIVERED = "ALREADY_DELIVERED"
ALREADY_FAILURE_NOTIFIED = "ALREADY_FAILURE_NOTIFIED"
REPORT_DELIVERY_SECRETS_REQUIRED = "REPORT_DELIVERY_SECRETS_REQUIRED"
REPORT_DELIVERY_CHANNELS_VERIFIED = "REPORT_DELIVERY_CHANNELS_VERIFIED"
MAX_DELIVERY_ATTEMPTS = 3

SILENT_FAILURE_STATUSES = frozenset(
    {
        "ALREADY_COMPLETED",
        ALREADY_DELIVERED,
        "SKIPPED_NON_TRADING_DAY",
        "SKIPPED_STALE_SCHEDULE",
        "PREFLIGHT_ONLY",
        "POST_CLOSE_DIAGNOSTIC_READY",
    }
)

REQUIRED_SECRET_NAMES = (
    "BARK_DEVICE_KEY",
    "REPORT_EMAIL_TO",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
)
_RECEIPT_STATUSES = {"SUCCESS", "FAILED", "NOT_CONFIGURED", "MISSING", "NOT_ATTEMPTED"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATE_TOKEN = re.compile(r"^\d{8}$")
_SAFE_LABEL = re.compile(r"[^A-Za-z0-9_.:/ -]+")
_RECEIPT_KEYS = {
    "schema_version",
    "report_date",
    "report_sha256",
    "candidate_count",
    "review_status",
    "shadow_status",
    "email_status",
    "email_sent_at_bjt",
    "bark_status",
    "bark_sent_at_bjt",
    "last_attempt_at_bjt",
    "email_error_summary",
    "bark_error_summary",
}
_FAILURE_NOTICE_STATUSES = {"SUCCESS", "FAILED", "NOT_CONFIGURED", "NOT_ATTEMPTED"}
_FAILURE_NOTICE_KEYS = {
    "schema_version",
    "report_date",
    "target_date",
    "first_failure_stage",
    "error_summary",
    "email_status",
    "bark_status",
    "first_attempt_at_bjt",
    "last_attempt_at_bjt",
    "email_sent_at_bjt",
    "bark_sent_at_bjt",
    "run_url",
}


class DeliveryError(ValueError):
    """A secret-free delivery/configuration error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DeliveryReceiptIdentityConflict(DeliveryError):
    """The receipt is bound to a different report byte identity."""

    def __init__(self) -> None:
        super().__init__("DELIVERY_RECEIPT_REPORT_IDENTITY_CONFLICT")


class SecretsRequired(DeliveryError):
    """The requested test delivery cannot run without configured secrets."""

    def __init__(self, missing: Sequence[str]) -> None:
        self.missing = tuple(missing)
        super().__init__(REPORT_DELIVERY_SECRETS_REQUIRED)


@dataclass(frozen=True)
class DeliverySettings:
    """Runtime settings with secret fields excluded from repr/debug output."""

    bark_device_key: str = field(repr=False)
    report_email_to: str = field(repr=False)
    smtp_host: str = field(repr=False)
    smtp_port: int
    smtp_username: str = field(repr=False)
    smtp_password: str = field(repr=False)
    smtp_from: str = field(repr=False)
    bark_server_url: str = field(repr=False)


@dataclass(frozen=True)
class ReportContext:
    report_date: str
    candidate_count: int
    review_status: str
    shadow_status: str
    report_path: Path
    report_sha256: str
    degraded_reasons: tuple[str, ...]
    input_coverage: dict[str, Any] | None = None

    @property
    def degraded(self) -> bool:
        return bool(self.degraded_reasons)


def normalize_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        text = str(value).strip().replace("/", "-")
        if len(text) == 8 and text.isdigit():
            text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
        try:
            parsed = date.fromisoformat(text)
        except ValueError as exc:
            raise DeliveryError("INVALID_REPORT_DATE") from exc
    return parsed.isoformat()


def _strict_iso_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        text = value.date().isoformat()
    elif isinstance(value, date):
        text = value.isoformat()
    else:
        text = str(value).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise DeliveryError("INVALID_TARGET_DATE")
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise DeliveryError("INVALID_TARGET_DATE") from exc
    if parsed.isoformat() != text:
        raise DeliveryError("INVALID_TARGET_DATE")
    return text


def _date_token(value: str) -> str:
    token = normalize_date(value).replace("-", "")
    if not _DATE_TOKEN.fullmatch(token):
        raise DeliveryError("INVALID_REPORT_DATE")
    return token


def _now_bjt(value: datetime | str | None = None) -> datetime:
    if value is None:
        return datetime.now(_BJT)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise DeliveryError("INVALID_NOW_BJT") from exc
    if value.tzinfo is None:
        value = value.replace(tzinfo=_BJT)
    return value.astimezone(_BJT)


def _timestamp(value: datetime) -> str:
    return _now_bjt(value).isoformat(timespec="seconds")


def _short_time(value: datetime) -> str:
    return _now_bjt(value).strftime("%H:%M")


def missing_secret_names(env: Mapping[str, str] | None = None) -> list[str]:
    environ = os.environ if env is None else env
    return [name for name in REQUIRED_SECRET_NAMES if not str(environ.get(name, "")).strip()]


def _channel_missing_secret_names(channel: str, env: Mapping[str, str]) -> list[str]:
    if channel == "email":
        return [
            name
            for name in REQUIRED_SECRET_NAMES
            if name != "BARK_DEVICE_KEY" and not str(env.get(name, "")).strip()
        ]
    if channel == "bark":
        return ["BARK_DEVICE_KEY"] if not str(env.get("BARK_DEVICE_KEY", "")).strip() else []
    raise DeliveryError("UNKNOWN_DELIVERY_CHANNEL")


def _settings(env: Mapping[str, str]) -> DeliverySettings:
    missing = missing_secret_names(env)
    if missing:
        raise SecretsRequired(missing)
    try:
        port = int(str(env["SMTP_PORT"]).strip())
    except (KeyError, TypeError, ValueError) as exc:
        raise DeliveryError("SMTP_PORT_INVALID") from exc
    if not 1 <= port <= 65535:
        raise DeliveryError("SMTP_PORT_INVALID")
    return DeliverySettings(
        bark_device_key=str(env["BARK_DEVICE_KEY"]).strip(),
        report_email_to=str(env["REPORT_EMAIL_TO"]).strip(),
        smtp_host=str(env["SMTP_HOST"]).strip(),
        smtp_port=port,
        smtp_username=str(env["SMTP_USERNAME"]).strip(),
        smtp_password=str(env["SMTP_PASSWORD"]),
        smtp_from=str(env.get("SMTP_FROM", "")).strip() or str(env["SMTP_USERNAME"]).strip(),
        bark_server_url=str(env.get("BARK_SERVER_URL", "")).strip() or DEFAULT_BARK_SERVER_URL,
    )


def _channel_settings(channel: str, env: Mapping[str, str]) -> DeliverySettings:
    missing = _channel_missing_secret_names(channel, env)
    if missing:
        raise SecretsRequired(missing)
    if channel == "bark":
        return DeliverySettings(
            bark_device_key=str(env["BARK_DEVICE_KEY"]).strip(),
            report_email_to="",
            smtp_host="",
            smtp_port=0,
            smtp_username="",
            smtp_password="",
            smtp_from="",
            bark_server_url=str(env.get("BARK_SERVER_URL", "")).strip() or DEFAULT_BARK_SERVER_URL,
        )
    try:
        port = int(str(env.get("SMTP_PORT", "")).strip())
    except (TypeError, ValueError) as exc:
        raise DeliveryError("SMTP_PORT_INVALID") from exc
    if not 1 <= port <= 65535:
        raise DeliveryError("SMTP_PORT_INVALID")
    report_to = str(env.get("REPORT_EMAIL_TO", "")).strip()
    if "\r" in report_to or "\n" in report_to:
        raise DeliveryError("REPORT_EMAIL_TO_INVALID")
    parsed = getaddresses([report_to])
    if not parsed or any(not address or "@" not in address for _name, address in parsed):
        raise DeliveryError("REPORT_EMAIL_TO_INVALID")
    username = str(env.get("SMTP_USERNAME", "")).strip()
    return DeliverySettings(
        bark_device_key="",
        report_email_to=report_to,
        smtp_host=str(env.get("SMTP_HOST", "")).strip(),
        smtp_port=port,
        smtp_username=username,
        smtp_password=str(env.get("SMTP_PASSWORD", "")),
        smtp_from=str(env.get("SMTP_FROM", "")).strip() or username,
        bark_server_url="",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DeliveryError("REPORT_READ_FAILED") from exc
    return digest.hexdigest()


def delivery_receipt_path(data_root: str | Path, report_date: date | datetime | str) -> Path:
    root = Path(data_root).expanduser().resolve()
    return root / "delivery" / f"daily_delivery_{_date_token(normalize_date(report_date))}.json"


def _read_json(path: Path, error_code: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeliveryError(error_code) from exc
    if not isinstance(value, Mapping):
        raise DeliveryError(error_code)
    return value


def _validate_bjt_timestamp(value: Any, *, required: bool) -> None:
    if value is None:
        if required:
            raise DeliveryError("DELIVERY_RECEIPT_INVALID")
        return
    if not isinstance(value, str):
        raise DeliveryError("DELIVERY_RECEIPT_INVALID")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DeliveryError("DELIVERY_RECEIPT_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(hours=8):
        raise DeliveryError("DELIVERY_RECEIPT_INVALID")


def validate_delivery_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    if not isinstance(receipt, Mapping) or set(receipt) - _RECEIPT_KEYS:
        raise DeliveryError("DELIVERY_RECEIPT_INVALID")
    required = {
        "schema_version",
        "report_date",
        "report_sha256",
        "candidate_count",
        "review_status",
        "shadow_status",
        "email_status",
        "email_sent_at_bjt",
        "bark_status",
        "bark_sent_at_bjt",
        "last_attempt_at_bjt",
    }
    if not required.issubset(receipt):
        raise DeliveryError("DELIVERY_RECEIPT_INVALID")
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise DeliveryError("DELIVERY_RECEIPT_INVALID")
    report_date = normalize_date(str(receipt.get("report_date", "")))
    if expected_date is not None and report_date != normalize_date(expected_date):
        raise DeliveryError("DELIVERY_RECEIPT_DATE_CONFLICT")
    if not isinstance(receipt.get("report_sha256"), str) or not _SHA256.fullmatch(receipt["report_sha256"]):
        raise DeliveryError("DELIVERY_RECEIPT_INVALID")
    candidate_count = receipt.get("candidate_count")
    if isinstance(candidate_count, bool) or not isinstance(candidate_count, int) or candidate_count < 0:
        raise DeliveryError("DELIVERY_RECEIPT_INVALID")
    for key in ("review_status", "shadow_status"):
        if not isinstance(receipt.get(key), str) or not receipt[key].strip():
            raise DeliveryError("DELIVERY_RECEIPT_INVALID")
    for key in ("email_status", "bark_status"):
        if receipt.get(key) not in _RECEIPT_STATUSES:
            raise DeliveryError("DELIVERY_RECEIPT_INVALID")
    _validate_bjt_timestamp(receipt.get("email_sent_at_bjt"), required=False)
    _validate_bjt_timestamp(receipt.get("bark_sent_at_bjt"), required=False)
    _validate_bjt_timestamp(receipt.get("last_attempt_at_bjt"), required=True)
    for status_key, sent_key in (
        ("email_status", "email_sent_at_bjt"),
        ("bark_status", "bark_sent_at_bjt"),
    ):
        if receipt[status_key] == "SUCCESS" and receipt[sent_key] is None:
            raise DeliveryError("DELIVERY_RECEIPT_INVALID")
    for key in ("email_error_summary", "bark_error_summary"):
        if key in receipt and receipt[key] is not None and (
            not isinstance(receipt[key], str) or len(receipt[key]) > 160
        ):
            raise DeliveryError("DELIVERY_RECEIPT_INVALID")
    return dict(receipt)


def load_delivery_receipt(
    data_root: str | Path,
    report_date: date | datetime | str,
) -> dict[str, Any] | None:
    path = delivery_receipt_path(data_root, report_date)
    if not path.exists():
        return None
    return validate_delivery_receipt(_read_json(path, "DELIVERY_RECEIPT_INVALID"), expected_date=report_date)


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise DeliveryError("DELIVERY_RECEIPT_WRITE_FAILED") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_delivery_receipt(
    data_root: str | Path,
    receipt: Mapping[str, Any],
) -> Path:
    validated = validate_delivery_receipt(receipt)
    path = delivery_receipt_path(data_root, validated["report_date"])
    _atomic_write_json(path, validated)
    return path


def failure_notice_path(data_root: str | Path, target_date: date | datetime | str) -> Path:
    root = Path(data_root).expanduser().resolve()
    return root / "delivery" / f"daily_failure_notice_{_date_token(normalize_date(target_date))}.json"


def validate_failure_notice(
    notice: Mapping[str, Any],
    *,
    expected_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    if not isinstance(notice, Mapping) or set(notice) - _FAILURE_NOTICE_KEYS:
        raise DeliveryError("FAILURE_NOTICE_INVALID")
    if not _FAILURE_NOTICE_KEYS.issubset(notice):
        raise DeliveryError("FAILURE_NOTICE_INVALID")
    if notice.get("schema_version") != FAILURE_NOTICE_SCHEMA_VERSION:
        raise DeliveryError("FAILURE_NOTICE_INVALID")
    report_date = _strict_iso_date(str(notice.get("report_date", "")))
    target_date = _strict_iso_date(str(notice.get("target_date", "")))
    if report_date != target_date:
        raise DeliveryError("FAILURE_NOTICE_DATE_CONFLICT")
    if expected_date is not None and report_date != _strict_iso_date(expected_date):
        raise DeliveryError("FAILURE_NOTICE_DATE_CONFLICT")
    for key in ("first_failure_stage", "error_summary"):
        value = notice.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 160:
            raise DeliveryError("FAILURE_NOTICE_INVALID")
    for key in ("email_status", "bark_status"):
        if notice.get(key) not in _FAILURE_NOTICE_STATUSES:
            raise DeliveryError("FAILURE_NOTICE_INVALID")
    _validate_bjt_timestamp(notice.get("first_attempt_at_bjt"), required=True)
    _validate_bjt_timestamp(notice.get("last_attempt_at_bjt"), required=True)
    _validate_bjt_timestamp(notice.get("email_sent_at_bjt"), required=False)
    _validate_bjt_timestamp(notice.get("bark_sent_at_bjt"), required=False)
    for status_key, sent_key in (
        ("email_status", "email_sent_at_bjt"),
        ("bark_status", "bark_sent_at_bjt"),
    ):
        if notice[status_key] == "SUCCESS" and notice[sent_key] is None:
            raise DeliveryError("FAILURE_NOTICE_INVALID")
    run_url = notice.get("run_url")
    if run_url is not None and (not isinstance(run_url, str) or len(run_url) > 500):
        raise DeliveryError("FAILURE_NOTICE_INVALID")
    return dict(notice)


def load_failure_notice(
    data_root: str | Path,
    target_date: date | datetime | str,
) -> dict[str, Any] | None:
    path = failure_notice_path(data_root, target_date)
    if not path.exists():
        return None
    return validate_failure_notice(
        _read_json(path, "FAILURE_NOTICE_INVALID"),
        expected_date=target_date,
    )


def write_failure_notice(data_root: str | Path, notice: Mapping[str, Any]) -> Path:
    validated = validate_failure_notice(notice)
    path = failure_notice_path(data_root, validated["target_date"])
    _atomic_write_json(path, validated)
    return path


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _result_bundle(result: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return _mapping(result.get("daily_close_bundle")) if isinstance(result, Mapping) else {}


def _review_status(
    report_date: str,
    data_root: Path,
    result: Mapping[str, Any] | None,
) -> str:
    bundle = _result_bundle(result)
    track = _mapping(bundle.get("track_perf"))
    coverage = _mapping(track.get("review_coverage"))
    if coverage.get("report_date") == report_date and coverage.get("status"):
        return str(coverage["status"])
    if track.get("status") == "FAILED":
        return "REVIEW_FAILED"
    bundle_status = str(bundle.get("status") or "")
    if bundle_status == "REVIEW_FAILED_REPORT_READY":
        return "REVIEW_FAILED"
    if bundle_status == "REVIEW_OBSERVATION_INCOMPLETE_REPORT_READY":
        return "REVIEW_OBSERVATION_INCOMPLETE"
    tracker_path = data_root / "perf_tracker.json"
    if tracker_path.is_file():
        tracker = _read_json(tracker_path, "REPORT_REVIEW_STATUS_UNAVAILABLE")
        stored = _mapping(tracker.get("review_coverage"))
        if stored.get("report_date") == report_date and stored.get("status"):
            return str(stored["status"])
    return "UNVERIFIED"


def _shadow_status(
    report_date: str,
    data_root: Path,
    candidate_count: int,
    result: Mapping[str, Any] | None,
) -> str:
    bundle = _result_bundle(result)
    shadow = _mapping(bundle.get("shadow_monitor"))
    capture = _mapping(shadow.get("capture"))
    if shadow.get("status"):
        return str(shadow["status"])
    if capture.get("status"):
        return str(capture["status"])
    shadow_path = data_root / "shadow_monitor" / "b_shadow_monitor.json"
    if shadow_path.is_file():
        store = _read_json(shadow_path, "REPORT_SHADOW_STATUS_UNAVAILABLE")
        last_capture = _mapping(store.get("last_capture"))
        if last_capture.get("signal_date") == report_date and last_capture.get("status"):
            return str(last_capture["status"])
        if candidate_count == 0:
            return "EMPTY"
    return "UNVERIFIED" if candidate_count else "EMPTY"


def _is_degraded_status(status: str, *, channel: str) -> bool:
    normalized = status.upper()
    if normalized in {"READY", "SUCCESS", "COMPLETE", "EMPTY"}:
        return False
    if channel == "review" and normalized == "T_PLUS_1_OBSERVATION_PENDING":
        return False
    return True


def load_report_context(
    data_root: str | Path,
    report_date: date | datetime | str,
    *,
    result: Mapping[str, Any] | None = None,
) -> ReportContext:
    normalized_date = normalize_date(report_date)
    token = _date_token(normalized_date)
    root = Path(data_root).expanduser().resolve()
    watchlist_path = root / f"watchlist_{token}.json"
    report_path = root / "reports" / f"daily_close_{token}.html"
    if not watchlist_path.is_file() or not report_path.is_file() or report_path.stat().st_size == 0:
        raise DeliveryError("REPORT_NOT_READY")
    watchlist = _read_json(watchlist_path, "WATCHLIST_READ_FAILED")
    candidates = watchlist.get("candidates")
    if not isinstance(candidates, list):
        raise DeliveryError("WATCHLIST_READ_FAILED")
    input_coverage = None
    if "input_coverage" in watchlist:
        try:
            input_coverage = validate_input_coverage(watchlist["input_coverage"])
        except ValueError as exc:
            raise DeliveryError("INPUT_COVERAGE_INVALID") from exc
    candidate_count = len(candidates)
    review_status = _review_status(normalized_date, root, result)
    shadow_status = _shadow_status(normalized_date, root, candidate_count, result)
    degraded_reasons: list[str] = []
    if _is_degraded_status(review_status, channel="review"):
        degraded_reasons.append(f"Review={review_status}")
    if _is_degraded_status(shadow_status, channel="shadow"):
        degraded_reasons.append(f"Shadow={shadow_status}")
    if isinstance(input_coverage, Mapping) and input_coverage.get("coverage_status") == INPUT_COVERAGE_DEGRADED:
        degraded_reasons.append(
            f"InputCoverage=DEGRADED/excluded={input_coverage.get('excluded_symbol_count')}"
        )
    bundle_status = str(_result_bundle(result).get("status") or "")
    if bundle_status == "REVIEW_FAILED_REPORT_READY" and "Review=REVIEW_FAILED" not in degraded_reasons:
        degraded_reasons.append("Review=REVIEW_FAILED")
    return ReportContext(
        report_date=normalized_date,
        candidate_count=candidate_count,
        review_status=review_status,
        shadow_status=shadow_status,
        report_path=report_path,
        report_sha256=file_sha256(report_path),
        degraded_reasons=tuple(degraded_reasons),
        input_coverage=input_coverage,
    )


def success_subject(report_date: str, sent_at: datetime, *, degraded: bool) -> str:
    subject = f"{_now_bjt(sent_at):%Y-%m-%d %H:%M} - A股每日收盘复盘报告"
    return f"{subject} - 数据不完整" if degraded else subject


def failure_subject(sent_at: datetime) -> str:
    return f"{_now_bjt(sent_at):%Y-%m-%d %H:%M} - A股云端运行失败"


def delivery_test_subject(sent_at: datetime) -> str:
    return f"{_now_bjt(sent_at):%Y-%m-%d %H:%M} - A股报告投递测试"


def success_attachment_filename(report_date: str, *, delivery_test: bool = False) -> str:
    prefix = "TEST_" if delivery_test else ""
    return f"{prefix}{normalize_date(report_date)}_A股每日收盘复盘报告.html"


def bark_title(report_date: str, sent_at: datetime, *, degraded: bool) -> str:
    del report_date
    suffix = " - A股每日复盘完成（数据不完整）" if degraded else " - A股每日收盘复盘完成"
    return f"{_short_time(sent_at)}{suffix}"


def failure_bark_title(sent_at: datetime) -> str:
    return f"{_short_time(sent_at)} - A股云端运行失败"


def delivery_test_bark_title(sent_at: datetime) -> str:
    return f"{_short_time(sent_at)} - A股报告投递测试"


def _run_url(value: str | None) -> str | None:
    text = str(value or "").strip()
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return text
    return None


def build_success_email_body(
    context: ReportContext,
    sent_at: datetime,
    *,
    runtime_state_persisted: str,
    run_url: str | None,
) -> str:
    filename = success_attachment_filename(context.report_date)
    lines = [
        f"报告日期：{context.report_date}",
        f"发送时间（北京时间）：{_now_bjt(sent_at):%Y-%m-%d %H:%M:%S}",
        f"运行状态：{'DEGRADED' if context.degraded else 'SUCCESS'}",
        f"候选数量：{context.candidate_count}",
        f"Review：{context.review_status}",
        f"Shadow：{context.shadow_status}",
        f"runtime-state：{runtime_state_persisted}",
        "Actions：production canonical chain ready",
    ]
    if context.degraded:
        lines.extend(["", "数据状态：数据不完整", "不完整项：" + "；".join(context.degraded_reasons)])
    if isinstance(context.input_coverage, Mapping) and context.input_coverage.get("coverage_status") == INPUT_COVERAGE_DEGRADED:
        lines.extend(
            [
                "",
                f"数据覆盖降级：排除 {context.input_coverage.get('excluded_symbol_count')} 只",
            ]
        )
    lines.extend(["", "完整复盘见附件：", filename])
    if _run_url(run_url):
        lines.extend(["", f"GitHub Actions run URL：{_run_url(run_url)}"])
    return "\n".join(lines) + "\n"


def build_success_bark_body(context: ReportContext, *, runtime_state_persisted: str) -> str:
    lines = [
        f"日期 {context.report_date}",
        f"候选数量 {context.candidate_count}",
        f"Review {context.review_status}",
        f"Shadow {context.shadow_status}",
        f"runtime-state persisted {runtime_state_persisted}",
    ]
    if isinstance(context.input_coverage, Mapping) and context.input_coverage.get("coverage_status") == INPUT_COVERAGE_DEGRADED:
        lines.append(f"数据覆盖降级：排除 {context.input_coverage.get('excluded_symbol_count')} 只")
    return "\n".join(lines)


def build_failure_email_body(
    report_date: str,
    sent_at: datetime,
    *,
    failure_stage: str,
    error_summary: str,
    run_url: str | None,
) -> str:
    lines = [
        f"目标交易日：{normalize_date(report_date)}",
        f"失败时间（北京时间）：{_now_bjt(sent_at):%Y-%m-%d %H:%M:%S}",
        "运行状态：FAILED",
        f"失败阶段：{_safe_label(failure_stage, 'UNKNOWN_STAGE')}",
        f"bounded error summary：{_safe_label(error_summary, 'PRODUCTION_RUNTIME_FAILURE')}",
        f"GitHub Actions run URL：{_run_url(run_url) or 'UNAVAILABLE'}",
        "本次运行未生成可交付的正式日报 HTML，未附加任何 HTML。",
    ]
    return "\n".join(lines) + "\n"


def build_delivery_test_email_body(report_date: str, sent_at: datetime, filename: str) -> str:
    return "\n".join(
        [
            "这是通知通道测试。",
            "不代表今日正式生产运行。",
            "附件来自当前 runtime-state latest report。",
            f"测试日期：{normalize_date(report_date)}",
            f"发送时间（北京时间）：{_now_bjt(sent_at):%Y-%m-%d %H:%M:%S}",
            "完整测试附件：",
            filename,
        ]
    ) + "\n"


def build_delivery_test_bark_body() -> str:
    return "通知通道测试成功\n非正式生产日报"


def build_email_message(
    *,
    subject: str,
    body: str,
    recipient: str,
    sender: str,
    attachment_path: Path | None = None,
    attachment_filename: str | None = None,
) -> EmailMessage:
    message = EmailMessage(policy=policy.SMTP)
    message["Subject"] = subject
    message["To"] = recipient
    message["From"] = sender
    message.set_content(body)
    if attachment_path is not None:
        if not attachment_filename:
            raise DeliveryError("ATTACHMENT_FILENAME_REQUIRED")
        try:
            payload = attachment_path.read_bytes()
        except OSError as exc:
            raise DeliveryError("REPORT_READ_FAILED") from exc
        message.add_attachment(
            payload,
            maintype="text",
            subtype="html",
            filename=attachment_filename,
        )
    return message


def send_email_message(message: EmailMessage, settings: DeliverySettings) -> None:
    context = ssl.create_default_context()
    client: Any
    if settings.smtp_port == 465:
        client = smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=30,
            context=context,
        )
        try:
            client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
        finally:
            try:
                client.quit()
            except Exception:
                pass
        return

    client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
    try:
        client.ehlo()
        client.starttls(context=context)
        client.ehlo()
        client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
    finally:
        try:
            client.quit()
        except Exception:
            pass


def _bark_endpoint(server_url: str) -> str:
    text = str(server_url or "").strip().rstrip("/")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DeliveryError("BARK_SERVER_URL_INVALID")
    return text if parsed.path.rstrip("/").endswith("/push") else f"{text}/push"


def send_bark_notification(
    *,
    settings: DeliverySettings,
    title: str,
    body: str,
    run_url: str | None,
) -> None:
    payload: dict[str, Any] = {
        "device_key": settings.bark_device_key,
        "title": title,
        "body": body,
    }
    safe_url = _run_url(run_url)
    if safe_url:
        payload["url"] = safe_url
    request = Request(
        _bark_endpoint(settings.bark_server_url),
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        response = urlopen(request, timeout=30)
        try:
            status = response.getcode()
            raw = response.read()
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    except HTTPError:
        raise
    except URLError:
        raise
    if status is not None and not 200 <= int(status) < 300:
        raise DeliveryError("BARK_HTTP_ERROR")
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = {}
    if isinstance(parsed, Mapping) and parsed.get("code") not in (None, 200, "200"):
        raise DeliveryError("BARK_API_REJECTED")


def _safe_label(
    value: Any,
    fallback: str,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    text = str(value or "").strip().splitlines()[0] if value is not None else ""
    if env is not None:
        secret_names = (*REQUIRED_SECRET_NAMES, "SMTP_FROM", "BARK_SERVER_URL")
        for name in secret_names:
            secret = str(env.get(name, "")).strip()
            if secret:
                text = text.replace(secret, "[REDACTED]")
    text = _SAFE_LABEL.sub("_", text)
    return text[:120] or fallback


def _error_summary(channel: str, exc: Exception) -> str:
    prefix = channel.upper()
    if isinstance(exc, HTTPError):
        return f"{prefix}_HTTP_{exc.code}"
    if isinstance(exc, URLError):
        return f"{prefix}_NETWORK_ERROR"
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "SMTP_AUTHENTICATION_FAILED"
    if isinstance(exc, smtplib.SMTPResponseException):
        return f"SMTP_RESPONSE_{exc.smtp_code}"
    if isinstance(exc, TimeoutError):
        return f"{prefix}_TIMEOUT"
    if isinstance(exc, DeliveryError):
        return exc.code
    return f"{prefix}_{type(exc).__name__.upper()}"


def _attempt(
    operation: Callable[[], None],
    *,
    channel: str,
    max_attempts: int,
    sleep_fn: Callable[[float], None],
) -> dict[str, Any]:
    attempts = min(MAX_DELIVERY_ATTEMPTS, max(1, int(max_attempts)))
    last_error = "UNKNOWN_DELIVERY_ERROR"
    for attempt_number in range(1, attempts + 1):
        try:
            operation()
            return {"status": "SUCCESS", "attempts": attempt_number, "error_summary": None}
        except Exception as exc:
            last_error = _error_summary(channel, exc)
            if attempt_number < attempts:
                sleep_fn(min(0.2 * (2 ** (attempt_number - 1)), 1.0))
    return {"status": "FAILED", "attempts": attempts, "error_summary": last_error}


def _base_receipt(context: ReportContext, now: datetime) -> dict[str, Any]:
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "report_date": context.report_date,
        "report_sha256": context.report_sha256,
        "candidate_count": context.candidate_count,
        "review_status": context.review_status,
        "shadow_status": context.shadow_status,
        "email_status": "MISSING",
        "email_sent_at_bjt": None,
        "bark_status": "MISSING",
        "bark_sent_at_bjt": None,
        "last_attempt_at_bjt": _timestamp(now),
        "email_error_summary": None,
        "bark_error_summary": None,
    }


def _overall_delivery_status(receipt: Mapping[str, Any]) -> str:
    email_ok = receipt.get("email_status") == "SUCCESS"
    bark_ok = receipt.get("bark_status") == "SUCCESS"
    if email_ok and bark_ok:
        return DELIVERY_SUCCESS
    if email_ok or bark_ok:
        return DELIVERY_DEGRADED
    return DELIVERY_FAILED


def _channel_result(
    channel: str,
    *,
    context: ReportContext,
    sent_at: datetime,
    runtime_state_persisted: str,
    run_url: str | None,
    env: Mapping[str, str],
    max_attempts: int,
    sleep_fn: Callable[[float], None],
) -> dict[str, Any]:
    missing = _channel_missing_secret_names(channel, env)
    if missing:
        return {"status": "NOT_CONFIGURED", "attempts": 0, "error_summary": "NOT_CONFIGURED"}
    try:
        settings = _channel_settings(channel, env)
        if channel == "email":
            message = build_email_message(
                subject=success_subject(context.report_date, sent_at, degraded=context.degraded),
                body=build_success_email_body(
                    context,
                    sent_at,
                    runtime_state_persisted=runtime_state_persisted,
                    run_url=run_url,
                ),
                recipient=settings.report_email_to,
                sender=settings.smtp_from,
                attachment_path=context.report_path,
                attachment_filename=success_attachment_filename(context.report_date),
            )
            operation = lambda: send_email_message(message, settings)
        else:
            operation = lambda: send_bark_notification(
                settings=settings,
                title=bark_title(context.report_date, sent_at, degraded=context.degraded),
                body=build_success_bark_body(context, runtime_state_persisted=runtime_state_persisted),
                run_url=run_url,
            )
        return _attempt(
            operation,
            channel=channel,
            max_attempts=max_attempts,
            sleep_fn=sleep_fn,
        )
    except (DeliveryError, OSError, ValueError) as exc:
        return {"status": "NOT_CONFIGURED", "attempts": 0, "error_summary": _error_summary(channel, exc)}


def deliver_production(
    data_root: str | Path,
    report_date: date | datetime | str,
    *,
    result: Mapping[str, Any] | None = None,
    run_url: str | None = None,
    runtime_state_persisted: str = "YES",
    env: Mapping[str, str] | None = None,
    now_bjt: datetime | str | None = None,
    max_attempts: int = 3,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    environ = os.environ if env is None else env
    now = _now_bjt(now_bjt)
    context = load_report_context(data_root, report_date, result=result)
    existing = load_delivery_receipt(data_root, context.report_date)
    if existing is not None and existing["report_sha256"] != context.report_sha256:
        raise DeliveryReceiptIdentityConflict()
    if existing is not None and (
        existing["email_status"] == "SUCCESS" and existing["bark_status"] == "SUCCESS"
    ):
        return {
            "status": ALREADY_DELIVERED,
            "report_date": context.report_date,
            "report_sha256": context.report_sha256,
            "candidate_count": context.candidate_count,
            "review_status": context.review_status,
            "shadow_status": context.shadow_status,
            "email_status": existing["email_status"],
            "bark_status": existing["bark_status"],
            "receipt_status": "PERSISTED",
            "receipt_path": str(delivery_receipt_path(data_root, context.report_date)),
            "attempted_channels": [],
        }

    receipt = dict(existing) if existing is not None else _base_receipt(context, now)
    receipt.update(
        {
            "report_date": context.report_date,
            "report_sha256": context.report_sha256,
            "candidate_count": context.candidate_count,
            "review_status": context.review_status,
            "shadow_status": context.shadow_status,
            "last_attempt_at_bjt": _timestamp(now),
        }
    )
    attempted: list[str] = []
    results: dict[str, dict[str, Any]] = {}
    for channel in ("email", "bark"):
        status_key = f"{channel}_status"
        if receipt.get(status_key) == "SUCCESS":
            results[channel] = {
                "status": "SUCCESS",
                "attempts": 0,
                "error_summary": receipt.get(f"{channel}_error_summary"),
            }
            continue
        attempted.append(channel)
        results[channel] = _channel_result(
            channel,
            context=context,
            sent_at=now,
            runtime_state_persisted=runtime_state_persisted,
            run_url=run_url,
            env=environ,
            max_attempts=max_attempts,
            sleep_fn=sleep_fn,
        )
        receipt[status_key] = results[channel]["status"]
        receipt[f"{channel}_error_summary"] = results[channel]["error_summary"]
        if results[channel]["status"] == "SUCCESS":
            receipt[f"{channel}_sent_at_bjt"] = _timestamp(now)
    receipt_path = write_delivery_receipt(data_root, receipt)
    return {
        "status": _overall_delivery_status(receipt),
        "report_date": context.report_date,
        "report_sha256": context.report_sha256,
        "candidate_count": context.candidate_count,
        "review_status": context.review_status,
        "shadow_status": context.shadow_status,
        "email_status": receipt["email_status"],
        "bark_status": receipt["bark_status"],
        "receipt_status": "PERSISTED",
        "receipt_path": str(receipt_path),
        "attempted_channels": attempted,
        "receipt": receipt,
    }


def _failure_error_summary(
    failure_stage: str,
    error_summary: str,
    result: Mapping[str, Any] | None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    if isinstance(result, Mapping):
        status = _safe_label(result.get("status"), "PRODUCTION_RUNTIME_FAILURE", env=env)
        error_type = _safe_label(result.get("error_type"), "", env=env)
        if error_type:
            return f"{status}/{error_type}"[:120]
    return (
        f"{_safe_label(failure_stage, 'UNKNOWN_STAGE', env=env)}/"
        f"{_safe_label(error_summary, 'PRODUCTION_RUNTIME_FAILURE', env=env)}"
    )[:120]


def _failure_channel_result(
    channel: str,
    *,
    report_date: str,
    sent_at: datetime,
    failure_stage: str,
    error_summary: str,
    result: Mapping[str, Any] | None,
    run_url: str | None,
    env: Mapping[str, str],
    max_attempts: int,
    sleep_fn: Callable[[float], None],
) -> dict[str, Any]:
    if _channel_missing_secret_names(channel, env):
        return {"status": "NOT_CONFIGURED", "attempts": 0, "error_summary": "NOT_CONFIGURED"}
    try:
        settings = _channel_settings(channel, env)
        bounded = _failure_error_summary(failure_stage, error_summary, result, env=env)
        if channel == "email":
            message = build_email_message(
                subject=failure_subject(sent_at),
                body=build_failure_email_body(
                    report_date,
                    sent_at,
                    failure_stage=failure_stage,
                    error_summary=bounded,
                    run_url=run_url,
                ),
                recipient=settings.report_email_to,
                sender=settings.smtp_from,
            )
            operation = lambda: send_email_message(message, settings)
        else:
            operation = lambda: send_bark_notification(
                settings=settings,
                title=failure_bark_title(sent_at),
                body="\n".join(
                    [
                        f"日期 {normalize_date(report_date)}",
                        "FAILED",
                        f"错误分类 {_safe_label(bounded, 'PRODUCTION_RUNTIME_FAILURE', env=env)}",
                    ]
                ),
                run_url=run_url,
            )
        return _attempt(operation, channel=channel, max_attempts=max_attempts, sleep_fn=sleep_fn)
    except (DeliveryError, OSError, ValueError) as exc:
        return {"status": "FAILED", "attempts": 0, "error_summary": _error_summary(channel, exc)}


def send_failure_notification(
    report_date: date | datetime | str,
    *,
    failure_stage: str,
    error_summary: str,
    run_url: str | None = None,
    result: Mapping[str, Any] | None = None,
    data_root: str | Path | None = None,
    production_status: str | None = None,
    env: Mapping[str, str] | None = None,
    now_bjt: datetime | str | None = None,
    max_attempts: int = 3,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    environ = os.environ if env is None else env
    normalized_date = normalize_date(report_date)
    status_text = str(production_status or "").strip()
    if status_text in SILENT_FAILURE_STATUSES or status_text.startswith("SKIPPED_"):
        return {
            "status": "FAILURE_NOTIFICATION_SUPPRESSED",
            "report_date": normalized_date,
            "target_date": normalized_date,
            "email_status": "NOT_ATTEMPTED",
            "bark_status": "NOT_ATTEMPTED",
            "attempted_channels": [],
            "receipt_status": "NOT_CREATED",
            "failure_notification": 0,
        }
    now = _now_bjt(now_bjt)
    existing = load_failure_notice(data_root, normalized_date) if data_root is not None else None
    if existing is not None and existing["email_status"] == "SUCCESS" and existing["bark_status"] == "SUCCESS":
        return {
            "status": ALREADY_FAILURE_NOTIFIED,
            "report_date": normalized_date,
            "target_date": normalized_date,
            "email_status": existing["email_status"],
            "bark_status": existing["bark_status"],
            "attempted_channels": [],
            "receipt_status": "PERSISTED",
            "failure_notice_status": ALREADY_FAILURE_NOTIFIED,
            "failure_notice_path": str(failure_notice_path(data_root, normalized_date)),
        }
    bounded = _failure_error_summary(failure_stage, error_summary, result, env=environ)
    results: dict[str, dict[str, Any]] = {}
    for channel in ("email", "bark"):
        if existing is not None and existing[f"{channel}_status"] == "SUCCESS":
            results[channel] = {"status": "SUCCESS", "attempts": 0, "error_summary": None}
            continue
        results[channel] = _failure_channel_result(
            channel,
            report_date=normalized_date,
            sent_at=now,
            failure_stage=failure_stage,
            error_summary=error_summary,
            result=result,
            run_url=run_url,
            env=environ,
            max_attempts=max_attempts,
            sleep_fn=sleep_fn,
        )
    statuses = {channel: value["status"] for channel, value in results.items()}
    if statuses["email"] == "SUCCESS" and statuses["bark"] == "SUCCESS":
        status = "FAILURE_NOTIFICATION_SENT"
    elif "SUCCESS" in statuses.values():
        status = "FAILURE_NOTIFICATION_DEGRADED"
    else:
        status = "FAILURE_NOTIFICATION_FAILED"
    receipt_status = "NOT_CREATED"
    notice_path = None
    if data_root is not None:
        notice = dict(existing) if existing is not None else {
            "schema_version": FAILURE_NOTICE_SCHEMA_VERSION,
            "report_date": normalized_date,
            "target_date": normalized_date,
            "first_failure_stage": _safe_label(failure_stage, "UNKNOWN_STAGE", env=environ)[:160],
            "error_summary": bounded[:160],
            "email_status": "NOT_ATTEMPTED",
            "bark_status": "NOT_ATTEMPTED",
            "first_attempt_at_bjt": _timestamp(now),
            "last_attempt_at_bjt": _timestamp(now),
            "email_sent_at_bjt": None,
            "bark_sent_at_bjt": None,
            "run_url": _run_url(run_url),
        }
        notice.update(
            {
                "report_date": normalized_date,
                "target_date": normalized_date,
                "last_attempt_at_bjt": _timestamp(now),
            }
        )
        if not notice.get("run_url") and _run_url(run_url):
            notice["run_url"] = _run_url(run_url)
        for channel in ("email", "bark"):
            notice[f"{channel}_status"] = results[channel]["status"]
            if results[channel]["status"] == "SUCCESS" and not (
                existing is not None and existing[f"{channel}_status"] == "SUCCESS"
            ):
                notice[f"{channel}_sent_at_bjt"] = _timestamp(now)
        try:
            persisted_path = write_failure_notice(data_root, notice)
        except (DeliveryError, OSError, ValueError):
            receipt_status = "NOT_PERSISTED"
        else:
            receipt_status = "PERSISTED"
            notice_path = str(persisted_path)
    return {
        "status": status,
        "report_date": normalized_date,
        "target_date": normalized_date,
        "email_status": statuses["email"],
        "bark_status": statuses["bark"],
        "attempted_channels": [channel for channel, value in results.items() if value["attempts"]],
        "receipt_status": receipt_status,
        "failure_notice_status": receipt_status,
        "failure_notice_path": notice_path,
    }


def send_delivery_test(
    data_root: str | Path,
    test_date: date | datetime | str,
    *,
    run_url: str | None = None,
    env: Mapping[str, str] | None = None,
    now_bjt: datetime | str | None = None,
    max_attempts: int = 3,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    environ = os.environ if env is None else env
    missing = missing_secret_names(environ)
    if missing:
        raise SecretsRequired(missing)
    settings = _settings(environ)
    now = _now_bjt(now_bjt)
    normalized_date = normalize_date(test_date)
    latest_path = Path(data_root).expanduser().resolve() / "reports" / "latest.html"
    if not latest_path.is_file() or latest_path.stat().st_size == 0:
        raise DeliveryError("LATEST_REPORT_NOT_READY")
    filename = success_attachment_filename(normalized_date, delivery_test=True)
    message = build_email_message(
        subject=delivery_test_subject(now),
        body=build_delivery_test_email_body(normalized_date, now, filename),
        recipient=settings.report_email_to,
        sender=settings.smtp_from,
        attachment_path=latest_path,
        attachment_filename=filename,
    )
    email_result = _attempt(
        lambda: send_email_message(message, settings),
        channel="email",
        max_attempts=max_attempts,
        sleep_fn=sleep_fn,
    )
    bark_result = _attempt(
        lambda: send_bark_notification(
            settings=settings,
            title=delivery_test_bark_title(now),
            body=build_delivery_test_bark_body(),
            run_url=run_url,
        ),
        channel="bark",
        max_attempts=max_attempts,
        sleep_fn=sleep_fn,
    )
    status = (
        REPORT_DELIVERY_CHANNELS_VERIFIED
        if email_result["status"] == "SUCCESS" and bark_result["status"] == "SUCCESS"
        else "REPORT_DELIVERY_CHANNELS_FAILED"
    )
    return {
        "status": status,
        "report_date": normalized_date,
        "email_status": email_result["status"],
        "bark_status": bark_result["status"],
        "attachment_filename": filename,
        "receipt_status": "NOT_CREATED",
        "runtime_state_mutation": "NO",
        "market_data_provider_calls": 0,
    }


def build_delivery_summary(
    data_root: str | Path,
    report_date: date | datetime | str,
    *,
    result: Mapping[str, Any] | None,
    production_status: str,
    runtime_state_persisted: str,
) -> str:
    normalized_date = normalize_date(report_date)
    value = result if isinstance(result, Mapping) else {}
    receipt = load_delivery_receipt(data_root, normalized_date)
    report_ready = "READY" if (Path(data_root).expanduser().resolve() / "reports" / f"daily_close_{_date_token(normalized_date)}.html").is_file() else "NOT_READY"
    watchlist_ready = "READY" if (Path(data_root).expanduser().resolve() / f"watchlist_{_date_token(normalized_date)}.json").is_file() else "NOT_READY"
    status = str(value.get("status") or "NOT_RUN")
    email_status = str(value.get("email_status") or (receipt or {}).get("email_status") or "NOT_RUN")
    bark_status = str(value.get("bark_status") or (receipt or {}).get("bark_status") or "NOT_RUN")
    candidate_count = value.get("candidate_count", (receipt or {}).get("candidate_count", "—"))
    receipt_status = str(value.get("receipt_status") or ("PERSISTED" if receipt else "NOT_CREATED"))
    return "\n".join(
        [
            "## Report delivery",
            "",
            f"SESSION_DATE = {normalized_date}",
            f"PRODUCTION = {production_status}",
            f"WATCHLIST = {watchlist_ready}",
            f"CANDIDATE_COUNT = {candidate_count}",
            f"REPORT = {report_ready}",
            f"RUNTIME_STATE = {runtime_state_persisted}",
            f"EMAIL = {email_status}",
            f"BARK = {bark_status}",
            f"DELIVERY_RECEIPT = {receipt_status}",
            "RAW_PERSISTED = 0",
            "FINAL_OOS_READ = NO",
            f"DELIVERY_RESULT = {status}",
            "",
        ]
    )


def _read_result_file(path: Path | None) -> Mapping[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        value = json.loads(lines[-1]) if lines else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _common_delivery_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--date", required=True)
    parser.add_argument("--run-url", default="")
    parser.add_argument("--now-bjt", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--max-attempts", type=int, default=3, help=argparse.SUPPRESS)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate-secrets")

    deliver = sub.add_parser("deliver")
    deliver.add_argument("--mode", choices=["production"], default="production")
    deliver.add_argument("--data-root", type=Path, required=True)
    _common_delivery_parser(deliver)
    deliver.add_argument("--runtime-state-persisted", choices=["YES", "NO"], default="YES")
    deliver.add_argument("--result-file", type=Path, default=None)

    test = sub.add_parser("delivery-test")
    test.add_argument("--data-root", type=Path, required=True)
    _common_delivery_parser(test)

    failure = sub.add_parser("failure")
    _common_delivery_parser(failure)
    failure.add_argument("--data-root", type=Path, default=None)
    failure.add_argument("--failure-stage", default="UNKNOWN_STAGE")
    failure.add_argument("--error-summary", default="PRODUCTION_RUNTIME_FAILURE")
    failure.add_argument("--production-status", default="")
    failure.add_argument("--result-file", type=Path, default=None)

    summary = sub.add_parser("summary")
    summary.add_argument("--data-root", type=Path, required=True)
    summary.add_argument("--date", required=True)
    summary.add_argument("--production-status", default="SUCCESS")
    summary.add_argument("--runtime-state-persisted", choices=["YES", "NO"], default="YES")
    summary.add_argument("--result-file", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    environ = os.environ
    try:
        if args.command == "validate-secrets":
            missing = missing_secret_names(environ)
            result = {"status": "READY" if not missing else REPORT_DELIVERY_SECRETS_REQUIRED}
            if missing:
                result["missing"] = missing
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0 if not missing else 1
        if args.command == "deliver":
            result = deliver_production(
                args.data_root,
                args.date,
                result=_read_result_file(args.result_file),
                run_url=args.run_url,
                runtime_state_persisted=args.runtime_state_persisted,
                now_bjt=args.now_bjt,
                max_attempts=args.max_attempts,
            )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "delivery-test":
            result = send_delivery_test(
                args.data_root,
                args.date,
                run_url=args.run_url,
                now_bjt=args.now_bjt,
                max_attempts=args.max_attempts,
            )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0 if result["status"] == REPORT_DELIVERY_CHANNELS_VERIFIED else 1
        if args.command == "failure":
            result = send_failure_notification(
                args.date,
                failure_stage=args.failure_stage,
                error_summary=args.error_summary,
                run_url=args.run_url,
                result=_read_result_file(args.result_file),
                data_root=args.data_root,
                production_status=args.production_status,
                now_bjt=args.now_bjt,
                max_attempts=args.max_attempts,
            )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "summary":
            print(
                build_delivery_summary(
                    args.data_root,
                    args.date,
                    result=_read_result_file(args.result_file),
                    production_status=args.production_status,
                    runtime_state_persisted=args.runtime_state_persisted,
                )
            )
            return 0
        raise DeliveryError("UNSUPPORTED_DELIVERY_COMMAND")
    except SecretsRequired as exc:
        result = {"status": exc.code, "missing": list(exc.missing)}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    except DeliveryError as exc:
        print(json.dumps({"status": "REPORT_DELIVERY_ERROR", "reason": exc.code}, ensure_ascii=False, sort_keys=True))
        return 1
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "REPORT_DELIVERY_ERROR", "reason": type(exc).__name__.upper()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
