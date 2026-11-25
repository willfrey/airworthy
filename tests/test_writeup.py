"""A write-up's log folds to one state by the transition table, or is refused."""

from datetime import UTC, date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Final

import pytest
from pydantic import ValidationError

from airworthy.writeup import (
    Closed,
    Due,
    Kind,
    Open,
    Overdue,
    Reclassified,
    RefusedError,
    Reopened,
    Reported,
    Resolved,
    Scheduled,
    Severity,
    Suggestion,
    Waiting,
    WriteUp,
    allowed,
    apply,
    downgraded,
    known_at,
    latest,
    opened,
    standing,
)

if TYPE_CHECKING:
    from airworthy.writeup import FollowUp

pytestmark = pytest.mark.unit

T0: Final = datetime(2026, 1, 10, 9, 0, tzinfo=UTC)
REPAIR_DAY: Final = date(2026, 1, 12)


def _at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def _reported(severity: Severity, minutes: int = 0) -> Reported:
    return Reported(
        at=_at(minutes), by="Ana Reyes", severity=severity, description="Cracked pane"
    )


def _reclassified(severity: Severity, minutes: int) -> Reclassified:
    return Reclassified(
        at=_at(minutes), by="Lin Zhou", severity=severity, reason="Measured the crack"
    )


def _scheduled(on: date, minutes: int) -> Scheduled:
    return Scheduled(at=_at(minutes), by="Dee Park", on=on)


def _resolved(minutes: int) -> Resolved:
    return Resolved(at=_at(minutes), by="Sam Okafor", note="Replaced the pane")


def _reopened(minutes: int) -> Reopened:
    return Reopened(at=_at(minutes), by="Ana Reyes", reason="Crack is back")


def _log(reported: Reported, *later: FollowUp) -> WriteUp:
    return WriteUp(id=1, tail="N101AW", reported=reported, later=later)


def _open(severity: Severity, scheduled_for: date | None, minutes: int) -> Open:
    return Open(severity=severity, scheduled_for=scheduled_for, as_of=_at(minutes))


def _closed(severity: Severity, resolved_at: int, as_of: int) -> Closed:
    return Closed(
        severity=severity,
        at=_at(resolved_at),
        by="Sam Okafor",
        note="Replaced the pane",
        as_of=_at(as_of),
    )


def _state_at(log: WriteUp, minutes: int) -> Open | Closed | None:
    known = known_at(log, _at(minutes))
    if known is None:
        return None
    return latest(known)


def _refusal(state: Open | Closed, event: FollowUp) -> str:
    with pytest.raises(RefusedError) as refused:
        _ = apply(state, event)
    return str(refused.value)


@pytest.mark.parametrize(
    ("severity", "grounds"),
    [(Severity.HIGH, True), (Severity.MEDIUM, False), (Severity.LOW, False)],
)
def test_only_a_high_severity_grounds(severity: Severity, *, grounds: bool) -> None:
    assert severity.grounds is grounds


def test_a_report_opens_a_write_up_unscheduled_at_its_severity() -> None:
    assert opened(_reported(Severity.MEDIUM)) == _open(Severity.MEDIUM, None, 0)


# The transition table, one test per cell.


def test_reclassifying_an_open_write_up_changes_its_severity_and_keeps_its_date() -> (
    None
):
    state = _open(Severity.MEDIUM, REPAIR_DAY, 5)

    moved = apply(state, _reclassified(Severity.HIGH, 10))

    assert moved == _open(Severity.HIGH, REPAIR_DAY, 10)


def test_scheduling_an_open_write_up_replaces_its_repair_date() -> None:
    state = _open(Severity.LOW, REPAIR_DAY, 5)

    moved = apply(state, _scheduled(date(2026, 1, 20), 10))

    assert moved == _open(Severity.LOW, date(2026, 1, 20), 10)


def test_resolving_an_open_write_up_closes_it_with_who_when_and_the_note() -> None:
    state = _open(Severity.HIGH, REPAIR_DAY, 5)

    moved = apply(state, _resolved(10))

    assert moved == _closed(Severity.HIGH, resolved_at=10, as_of=10)


def test_reopening_an_open_write_up_is_refused() -> None:
    refusal = _refusal(_open(Severity.HIGH, None, 5), _reopened(10))

    assert refusal == "this write-up is already open"


def test_reclassifying_a_resolved_write_up_changes_only_its_severity() -> None:
    state = _closed(Severity.HIGH, resolved_at=5, as_of=5)

    moved = apply(state, _reclassified(Severity.LOW, 10))

    assert moved == _closed(Severity.LOW, resolved_at=5, as_of=10)


def test_scheduling_a_resolved_write_up_is_refused() -> None:
    state = _closed(Severity.HIGH, resolved_at=5, as_of=5)

    refusal = _refusal(state, _scheduled(REPAIR_DAY, 10))

    assert refusal == "a resolved write-up can't be scheduled; reopen it first"


def test_resolving_a_resolved_write_up_is_refused() -> None:
    state = _closed(Severity.HIGH, resolved_at=5, as_of=5)

    refusal = _refusal(state, _resolved(10))

    assert refusal == "this write-up is already resolved"


def test_reopening_a_resolved_write_up_opens_it_with_no_repair_date() -> None:
    state = _closed(Severity.MEDIUM, resolved_at=5, as_of=5)

    moved = apply(state, _reopened(10))

    assert moved == _open(Severity.MEDIUM, None, 10)


def test_an_event_dated_before_the_last_one_is_refused() -> None:
    refusal = _refusal(_open(Severity.LOW, None, 5), _resolved(4))

    assert refusal == "an event can't be dated before the write-up's last event"


def test_an_event_dated_at_the_same_instant_as_the_last_one_is_applied() -> None:
    moved = apply(_open(Severity.LOW, None, 5), _resolved(5))

    assert moved == _closed(Severity.LOW, resolved_at=5, as_of=5)


# Awkward paths, each folded from a whole log.


def test_a_write_up_has_no_state_before_its_report() -> None:
    log = _log(_reported(Severity.HIGH, minutes=10))

    assert _state_at(log, 9) is None


def test_a_write_up_is_open_at_the_instant_of_its_report() -> None:
    log = _log(_reported(Severity.HIGH, minutes=10))

    assert _state_at(log, 10) == _open(Severity.HIGH, None, 10)


def test_a_write_up_known_at_a_moment_holds_only_the_events_dated_by_then() -> None:
    scheduled = _scheduled(REPAIR_DAY, 5)
    log = _log(_reported(Severity.HIGH), scheduled, _resolved(10))

    assert known_at(log, _at(9)) == _log(_reported(Severity.HIGH), scheduled)
    assert known_at(log, _at(10)) == log


def test_a_follow_up_dated_exactly_at_the_moment_read_is_applied() -> None:
    log = _log(_reported(Severity.HIGH), _resolved(10))

    assert _state_at(log, 10) == _closed(Severity.HIGH, resolved_at=10, as_of=10)


def test_a_follow_up_dated_after_the_moment_read_is_not_applied() -> None:
    log = _log(_reported(Severity.HIGH), _scheduled(REPAIR_DAY, 5), _resolved(10))

    assert _state_at(log, 9) == _open(Severity.HIGH, REPAIR_DAY, 5)


def test_raising_a_medium_to_high_leaves_it_open_and_high() -> None:
    log = _log(_reported(Severity.MEDIUM), _reclassified(Severity.HIGH, 10))

    assert _state_at(log, 10) == _open(Severity.HIGH, None, 10)


def test_lowering_a_high_leaves_it_open_at_the_lower_severity() -> None:
    log = _log(_reported(Severity.HIGH), _reclassified(Severity.MEDIUM, 10))

    assert _state_at(log, 10) == _open(Severity.MEDIUM, None, 10)


def test_a_reopened_high_is_open_and_high_again() -> None:
    log = _log(
        _reported(Severity.HIGH),
        _scheduled(REPAIR_DAY, 5),
        _resolved(10),
        _reopened(15),
    )

    assert _state_at(log, 15) == _open(Severity.HIGH, None, 15)


def test_a_write_up_can_be_resolved_without_ever_being_scheduled() -> None:
    log = _log(_reported(Severity.LOW), _resolved(10))

    assert _state_at(log, 20) == _closed(Severity.LOW, resolved_at=10, as_of=10)


def test_a_severity_corrected_while_resolved_is_the_severity_it_reopens_at() -> None:
    log = _log(
        _reported(Severity.MEDIUM),
        _resolved(10),
        _reclassified(Severity.HIGH, 15),
        _reopened(20),
    )

    assert _state_at(log, 20) == _open(Severity.HIGH, None, 20)


def test_events_at_one_instant_apply_in_log_order() -> None:
    log = _log(_reported(Severity.HIGH), _scheduled(REPAIR_DAY, 10), _resolved(10))

    assert _state_at(log, 10) == _closed(Severity.HIGH, resolved_at=10, as_of=10)


@pytest.mark.parametrize("minutes", [-1, 5, 10, 20])
def test_a_log_holding_a_refused_follow_up_fails_at_every_moment_read(
    minutes: int,
) -> None:
    """Before the report, before the refused follow-up, at it and after it."""
    log = _log(_reported(Severity.HIGH), _resolved(10), _scheduled(REPAIR_DAY, 10))

    with pytest.raises(RefusedError):
        _ = known_at(log, _at(minutes))


# Where a write-up stands.


def test_an_open_write_up_with_no_repair_date_is_waiting_at_any_moment() -> None:
    state = _open(Severity.LOW, None, 0)

    assert standing(state, _at(0)) == Waiting()
    assert standing(state, _at(60 * 24 * 30)) == Waiting()


@pytest.mark.parametrize(
    ("moment", "is_overdue"),
    [
        (datetime(2026, 1, 11, 12, 0, tzinfo=UTC), False),
        (datetime(2026, 1, 12, 23, 59, tzinfo=UTC), False),
        (datetime(2026, 1, 13, 0, 0, tzinfo=UTC), True),
        # Still the repair day in New York, already the next day in UTC.
        (datetime(2026, 1, 12, 20, 0, tzinfo=timezone(timedelta(hours=-5))), True),
        # Already the next day in Tokyo, still the repair day in UTC.
        (datetime(2026, 1, 13, 8, 0, tzinfo=timezone(timedelta(hours=9))), False),
    ],
)
def test_an_open_write_up_is_overdue_once_its_repair_date_is_past_in_utc(
    moment: datetime, *, is_overdue: bool
) -> None:
    stands = Overdue(on=REPAIR_DAY) if is_overdue else Due(on=REPAIR_DAY)

    assert standing(_open(Severity.LOW, REPAIR_DAY, 0), moment) == stands


def test_a_resolved_write_up_stands_as_its_state_however_late() -> None:
    state = _closed(Severity.LOW, resolved_at=0, as_of=0)

    assert standing(state, _at(60 * 24 * 30)) == state


# What an event may hold.


def test_a_follow_up_with_one_bad_field_reports_that_field_once() -> None:
    """A log's follow-ups are told apart by `kind`, not tried one after another."""
    log: dict[str, object] = {
        "id": 1,
        "tail": "N101AW",
        "reported": _reported(Severity.LOW),
        "later": [{"kind": "scheduled", "at": T0, "by": "Dee Park", "on": "someday"}],
    }

    with pytest.raises(ValidationError, match="valid date") as invalid:
        _ = WriteUp.model_validate(log)

    places = [error["loc"] for error in invalid.value.errors()]
    assert places == [("later", 0, "scheduled", "on")]


def test_an_event_strips_its_text() -> None:
    resolved = Resolved(at=T0, by="  Sam Okafor ", note=" Replaced the pane\n")

    assert (resolved.by, resolved.note) == ("Sam Okafor", "Replaced the pane")


def test_an_event_rejects_a_blank_name() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        _ = Resolved(at=T0, by="   ", note="Replaced the pane")


def test_an_event_rejects_a_time_with_no_zone() -> None:
    naive = datetime(2026, 1, 10, 9, 0)  # ruff: ignore[call-datetime-without-tzinfo] — the input under test

    with pytest.raises(ValidationError, match="timezone"):
        _ = Resolved(at=naive, by="Sam Okafor", note="Replaced the pane")


def test_a_state_allows_exactly_the_follow_ups_the_table_gives_it() -> None:
    assert allowed(_open(Severity.HIGH, None, 0)) == (
        Kind.SCHEDULED,
        Kind.RESOLVED,
        Kind.RECLASSIFIED,
    )
    assert allowed(_closed(Severity.HIGH, 5, 5)) == (Kind.REOPENED, Kind.RECLASSIFIED)


@pytest.mark.parametrize(
    ("severity", "other", "below"),
    [
        (Severity.LOW, Severity.MEDIUM, True),
        (Severity.LOW, Severity.HIGH, True),
        (Severity.MEDIUM, Severity.HIGH, True),
        (Severity.MEDIUM, Severity.MEDIUM, False),
        (Severity.MEDIUM, Severity.LOW, False),
        (Severity.HIGH, Severity.MEDIUM, False),
        (Severity.HIGH, Severity.LOW, False),
    ],
)
def test_a_severity_is_below_only_a_more_serious_one(
    severity: Severity, other: Severity, *, below: bool
) -> None:
    """Medium below high is the case a string comparison gets wrong."""
    assert severity.below(other) is below


@pytest.mark.parametrize(
    ("picked", "suggested", "expected"),
    [
        (Severity.MEDIUM, Severity.HIGH, True),
        (Severity.HIGH, Severity.HIGH, False),
        (Severity.HIGH, Severity.LOW, False),
        (Severity.LOW, None, False),
    ],
)
def test_a_report_is_downgraded_only_when_filed_below_its_suggestion(
    picked: Severity, suggested: Severity | None, *, expected: bool
) -> None:
    suggestion = (
        None
        if suggested is None
        else Suggestion(severity=suggested, reason="Looks loose")
    )
    reported = Reported(
        at=_at(0),
        by="Ana Reyes",
        severity=picked,
        description="Loose panel",
        suggested=suggestion,
    )

    assert downgraded(reported) is expected


def test_a_suggestion_needs_a_reason() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        _ = Suggestion(severity=Severity.HIGH, reason="  ")
