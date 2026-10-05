from __future__ import annotations

from copy import deepcopy

from audit_entry_validity_semantics_impact import (
    CATEGORY_A,
    CATEGORY_B,
    MODEL_P,
    MODEL_R,
    _primary_metrics,
    compare_pair,
)
from trading_calendar import default_calendar
from track_perf import (
    EXIT_REASON_EXPIRED_UNTRIGGERED,
    EXIT_REASON_STOP,
    EXIT_REASON_TARGET,
    EXIT_REASON_TIME,
    PERFORMANCE_DATA_INCOMPLETE,
    RULE_STATUS_CLOSED,
    RULE_STATUS_OPEN,
)


CALENDAR = default_calendar()
SIGNAL_DATE = "2026-09-03"
T1 = "2026-09-04"
T10 = "2026-09-17"
T11 = "2026-09-18"
T12 = "2026-09-21"


def _prospective(**overrides):
    row = {
        "signal_id": "S-1",
        "signal_date": SIGNAL_DATE,
        "delay_status": "KNOWN",
        "first_trigger_date": T1,
        "first_trigger_delay": 1,
        "operational_path_status": "COMPLETE",
        "operational_execution_verification_status": "VERIFIED",
        "operational_entry_date": T1,
        "operational_entry_price": 100.0,
        "operational_exit_date": T10,
        "operational_exit_reason": EXIT_REASON_TIME,
        "operational_terminal_status": "TIME_EXIT",
        "operational_return_pct": -2.0,
        "operational_holding_sessions": 10,
        "missing_sessions": [],
    }
    row.update(overrides)
    return row


def _rule(**overrides):
    row = {
        "signal_id": "S-1",
        "signal_date": SIGNAL_DATE,
        "status": RULE_STATUS_CLOSED,
        "historical_data_status": "COMPLETE",
        "entry_date": T1,
        "trigger_date": T1,
        "entry_price": 100.0,
        "exit_date": T12,
        "exit_reason": EXIT_REASON_TARGET,
        "realized_return_pct": 10.0,
        "holding_sessions": 13,
        "reason": None,
    }
    row.update(overrides)
    return row


def test_t10_untriggered_vs_t11_rule_entry_is_category_a_and_complete():
    p = _prospective(
        delay_status="UNTRIGGERED",
        first_trigger_date=None,
        first_trigger_delay=None,
        operational_entry_date=None,
        operational_entry_price=None,
        operational_exit_date=T10,
        operational_exit_reason=EXIT_REASON_EXPIRED_UNTRIGGERED,
        operational_terminal_status="EXPIRED_UNTRIGGERED",
        operational_return_pct=None,
        operational_holding_sessions=None,
    )
    r = _rule(entry_date=T11, trigger_date=T11, exit_date=T12)

    flags = compare_pair(p, r, calendar=CALENDAR)

    assert flags["category_a_exact"] is True
    assert flags["category_a_evidence_status"] == "COMPLETE"
    assert flags["category_b_exact"] is False
    assert flags["r_first_trigger_delay"] == 11


def test_t10_first_trigger_is_not_an_earlier_entry_time_exit_mismatch():
    p = _prospective(first_trigger_date=T10, first_trigger_delay=10, operational_entry_date=T10)
    r = _rule(entry_date=T10, trigger_date=T10, exit_date=T12)

    flags = compare_pair(p, r, calendar=CALENDAR)

    assert flags["category_b_entry_identity_comparable"] is True
    assert flags["category_b_exact"] is False
    assert flags["category_a_exact"] is False


def test_early_entry_time_exit_later_target_and_metric_delta():
    p = _prospective()
    r = _rule()
    before = (deepcopy(p), deepcopy(r))
    flags = compare_pair(p, r, calendar=CALENDAR)
    pair = {"prospective": p, "rule": r, "flags": flags}
    metrics = _primary_metrics([pair])

    assert flags["category_b_entry_identity_comparable"] is True
    assert flags["category_b_exact"] is True
    assert flags["category_b_outcome"] == "LATER_TARGET"
    assert flags["return_delta_pct"] == 12.0
    assert metrics[MODEL_P]["time_exit_count"] == 1
    assert metrics[MODEL_R]["time_exit_count"] == 0
    assert metrics[MODEL_P]["target_count"] == 0
    assert metrics[MODEL_R]["target_count"] == 1
    assert metrics["delta_MODEL_R_minus_MODEL_P"]["closed_trades"] == 0
    assert p == before[0]
    assert r == before[1]


def test_early_entry_time_exit_later_stop_or_remaining_open_is_classified():
    for r, expected in (
        (_rule(exit_reason=EXIT_REASON_STOP, realized_return_pct=-5.0), "LATER_STOP"),
        (_rule(status=RULE_STATUS_OPEN, exit_date=None, exit_reason=None, realized_return_pct=None, holding_sessions=None), "REMAINS_OPEN"),
    ):
        flags = compare_pair(_prospective(), r, calendar=CALENDAR)
        assert flags["category_b_exact"] is True
        assert flags["category_b_outcome"] == expected


def test_incomplete_pre_or_post_path_is_unresolved_not_an_exact_mismatch():
    p = _prospective(
        delay_status="INCOMPLETE",
        first_trigger_date=None,
        first_trigger_delay=None,
        operational_path_status="INCOMPLETE",
        operational_entry_date=None,
        operational_entry_price=None,
        operational_exit_date=None,
        operational_exit_reason=None,
        operational_terminal_status="OPEN_OR_PENDING",
        operational_return_pct=None,
        operational_holding_sessions=None,
    )
    r = _rule(
        status=PERFORMANCE_DATA_INCOMPLETE,
        historical_data_status="INCOMPLETE",
        entry_date=None,
        trigger_date=None,
        exit_date=None,
        exit_reason=None,
        realized_return_pct=None,
        holding_sessions=None,
    )

    flags = compare_pair(p, r, calendar=CALENDAR)

    assert flags["category_a_exact"] is False
    assert flags["category_a_unresolved_candidate"] is True
    assert flags["category_b_exact"] is False


def test_category_a_and_b_are_mutually_exclusive_and_denominators_are_explicit():
    a_p = _prospective(
        delay_status="UNTRIGGERED",
        first_trigger_date=None,
        first_trigger_delay=None,
        operational_entry_date=None,
        operational_entry_price=None,
        operational_exit_reason=EXIT_REASON_EXPIRED_UNTRIGGERED,
        operational_terminal_status="EXPIRED_UNTRIGGERED",
        operational_return_pct=None,
        operational_holding_sessions=None,
    )
    a_r = _rule(entry_date=T11, trigger_date=T11)
    a_flags = compare_pair(a_p, a_r, calendar=CALENDAR)
    b_flags = compare_pair(_prospective(), _rule(), calendar=CALENDAR)

    assert not (a_flags["category_a_exact"] and a_flags["category_b_exact"])
    assert not (b_flags["category_a_exact"] and b_flags["category_b_exact"])
    metrics = _primary_metrics([{"prospective": _prospective(), "rule": _rule(), "flags": b_flags}])
    assert metrics["denominators"]["trigger_rate"] == "eligible_signals"
    assert metrics["denominators"]["target_rate"] == "closed_trades"
