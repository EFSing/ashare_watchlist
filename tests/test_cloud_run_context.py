from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from cloud_runtime_state import (
    RUN_CONTEXT_READY,
    SKIPPED_STALE_SCHEDULE,
    RuntimeStateError,
    resolve_run_context,
)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_schedule_binds_primary_and_retry_to_utc_calendar_date():
    primary = resolve_run_context(
        event_name="schedule",
        schedule="17 9 * * 1-5",
        now_utc=_utc("2026-09-14T09:31:00Z"),
    )
    retry = resolve_run_context(
        event_name="schedule",
        schedule="17 10 * * 1-5",
        now_utc=_utc("2026-09-14T10:31:00Z"),
    )

    assert primary["status"] == RUN_CONTEXT_READY
    assert primary["target_date"] == "2026-09-14"
    assert retry["status"] == RUN_CONTEXT_READY
    assert retry["target_date"] == "2026-09-14"


def test_same_day_late_schedule_remains_eligible_for_idempotency_or_bounded_retry():
    result = resolve_run_context(
        event_name="schedule",
        schedule="17 9 * * 1-5",
        now_utc=_utc("2026-09-14T15:54:00Z"),
    )

    assert result["status"] == RUN_CONTEXT_READY
    assert result["target_date"] == "2026-09-14"
    assert result["production_allowed"] is True


def test_cross_midnight_schedule_is_stale_without_provider_or_failure_delivery():
    result = resolve_run_context(
        event_name="schedule",
        schedule="17 10 * * 1-5",
        now_utc=_utc("2026-09-14T16:22:00Z"),  # 2026-09-15 00:22 BJT
    )

    assert result["status"] == SKIPPED_STALE_SCHEDULE
    assert result["target_date"] == "2026-09-14"
    assert result["reason"] == "SCHEDULE_CROSSED_BJT_MIDNIGHT"
    assert result["provider_calls"] == 0
    assert result["failure_notification"] == 0
    assert result["production_allowed"] is False


def test_external_dispatch_date_is_immutable_and_not_wall_clock_derived():
    result = resolve_run_context(
        event_name="workflow_dispatch",
        trigger_source="cloudflare-cron",
        as_of_date="2026-09-15",
        mode="production",
        now_utc=_utc("2026-09-16T02:22:00Z"),
    )

    assert result["status"] == RUN_CONTEXT_READY
    assert result["target_date"] == "2026-09-15"
    assert result["target_date_source"] == "explicit_dispatch_input"


def test_external_production_dispatch_requires_a_strict_iso_date():
    with pytest.raises(RuntimeStateError, match="EXTERNAL_PRODUCTION_AS_OF_DATE_REQUIRED"):
        resolve_run_context(
            event_name="workflow_dispatch",
            trigger_source="external-scheduler",
            mode="production",
            now_utc=_utc("2026-09-15T09:00:00Z"),
        )
    with pytest.raises(RuntimeStateError, match="INVALID_AS_OF_DATE"):
        resolve_run_context(
            event_name="workflow_dispatch",
            trigger_source="cloudflare-cron",
            as_of_date="2026/09/15",
            mode="production",
            now_utc=_utc("2026-09-15T09:00:00Z"),
        )


def test_workflow_has_explicit_date_binding_and_stale_skip_gate():
    workflow = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily_t_close.yml"
    ).read_text(encoding="utf-8")

    assert "as_of_date:" in workflow
    assert "trigger_source:" in workflow
    assert "resolve-context" in workflow
    assert "SKIPPED_STALE_SCHEDULE" in workflow
    assert "STALE_SCHEDULE=1" in workflow
    assert "ASHARE_SKIP_PRODUCTION=1" in workflow
    assert "failure-runtime-state" in workflow
    assert "persist-failure-notice" in workflow
    assert "daily_failure_notice_${AS_OF_DATE//-/}.json" in workflow
    assert "datetime.now(timezone.utc).astimezone" not in workflow
