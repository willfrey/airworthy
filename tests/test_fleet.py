"""An aircraft is grounded exactly while one of its write-ups is open and high."""

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Final

import pytest
from hypothesis import given, strategies as st

from airworthy.fleet import Cleared, Grounded, status_at
from airworthy.writeup import (
    Reclassified,
    RefusedError,
    Reopened,
    Reported,
    Resolved,
    Scheduled,
    Severity,
    WriteUp,
    apply,
    opened,
)

if TYPE_CHECKING:
    from airworthy.fleet import Status
    from airworthy.writeup import FollowUp, State

pytestmark = pytest.mark.unit

T0: Final = datetime(2026, 1, 10, 9, 0, tzinfo=UTC)


def _at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def _write_up(number: int, severity: Severity, *later: FollowUp) -> WriteUp:
    reported = Reported(
        at=_at(0), by="Ana Reyes", severity=severity, description="Cracked pane"
    )
    return WriteUp(id=number, tail="N101AW", reported=reported, later=later)


def _resolved(minutes: int) -> Resolved:
    return Resolved(at=_at(minutes), by="Sam Okafor", note="Replaced the pane")


def _grounding(status: Status) -> list[int]:
    """Give the ids of the write-ups a status names, none for a cleared aircraft."""
    match status:
        case Grounded(by=by):
            return [write_up.id for write_up in by]
        case Cleared():
            return []


def test_an_aircraft_with_no_write_ups_is_cleared() -> None:
    assert status_at([], _at(0)) == Cleared()


def test_an_open_high_grounds_its_aircraft_and_is_named() -> None:
    high = _write_up(1, Severity.HIGH)

    assert status_at([high], _at(0)) == Grounded(by=(high,))


def test_open_mediums_and_lows_leave_an_aircraft_cleared() -> None:
    write_ups = [_write_up(1, Severity.MEDIUM), _write_up(2, Severity.LOW)]

    assert status_at(write_ups, _at(0)) == Cleared()


def test_a_grounded_aircraft_names_every_open_high_and_nothing_else() -> None:
    first = _write_up(1, Severity.HIGH)
    medium = _write_up(2, Severity.MEDIUM)
    second = _write_up(3, Severity.HIGH)
    fixed = _write_up(4, Severity.HIGH, _resolved(5))

    status = status_at([first, medium, second, fixed], _at(10))

    assert status == Grounded(by=(first, second))


def test_an_aircraft_is_cleared_once_its_only_high_is_resolved() -> None:
    fixed = _write_up(1, Severity.HIGH, _resolved(5))

    assert status_at([fixed], _at(5)) == Cleared()


def test_an_aircraft_is_cleared_before_its_high_was_reported() -> None:
    high = _write_up(1, Severity.HIGH)

    assert status_at([high], _at(-1)) == Cleared()


# The laws, over generated histories. Candidate follow-ups are drawn freely and kept
# only when `apply` accepts them, so every generated log is one the app could hold.

_instants: Final = st.integers(0, 20).map(_at)
_names: Final = st.just("Sam Okafor")
_texts: Final = st.just("Noted on the walk-round")
_follow_ups: Final = st.one_of(
    st.builds(
        Reclassified,
        at=_instants,
        by=_names,
        severity=st.sampled_from(Severity),
        reason=_texts,
    ),
    st.builds(Scheduled, at=_instants, by=_names, on=st.just(date(2026, 1, 12))),
    st.builds(Resolved, at=_instants, by=_names, note=_texts),
    st.builds(Reopened, at=_instants, by=_names, reason=_texts),
)
_reports: Final = st.builds(
    Reported,
    at=_instants,
    by=_names,
    severity=st.sampled_from(Severity),
    description=_texts,
)


@st.composite
def _histories(draw: st.DrawFn) -> list[WriteUp]:
    """Draw one aircraft's write-ups, each a log `apply` accepts, with distinct ids."""
    write_ups: list[WriteUp] = []
    for number, reported in enumerate(draw(st.lists(_reports, max_size=4))):
        candidates = sorted(
            draw(st.lists(_follow_ups, max_size=8)), key=lambda event: event.at
        )
        state: State = opened(reported)
        later: list[FollowUp] = []
        for event in candidates:
            try:
                state = apply(state, event)
            except RefusedError:
                continue
            later.append(event)
        write_ups.append(
            WriteUp(id=number, tail="N101AW", reported=reported, later=tuple(later))
        )
    return write_ups


# This calls neither `state_at` nor `Severity.grounds`, so the property below compares
# the code with an answer the code did not help produce.
def _grounds_by_hand(write_up: WriteUp, t: datetime) -> bool:
    """Work out from the raw events alone whether a write-up grounds at `t`."""
    if write_up.reported.at > t:
        return False
    seen = [event for event in write_up.later if event.at <= t]
    lifecycle = [event for event in seen if isinstance(event, Resolved | Reopened)]
    is_open = not lifecycle or isinstance(lifecycle[-1], Reopened)
    severities = [
        write_up.reported.severity,
        *(event.severity for event in seen if isinstance(event, Reclassified)),
    ]
    return is_open and severities[-1] is Severity.HIGH


@given(write_ups=_histories(), t=_instants)
def test_an_aircraft_is_grounded_exactly_by_its_open_highs(
    write_ups: list[WriteUp], t: datetime
) -> None:
    expected = [w.id for w in write_ups if _grounds_by_hand(w, t)]

    assert _grounding(status_at(write_ups, t)) == expected


@given(write_ups=_histories(), t=_instants)
def test_events_after_a_moment_never_change_the_status_at_it(
    write_ups: list[WriteUp], t: datetime
) -> None:
    """A past view is trustworthy only if nothing recorded later can alter it."""
    known_then = [
        WriteUp(
            id=w.id,
            tail=w.tail,
            reported=w.reported,
            later=tuple(event for event in w.later if event.at <= t),
        )
        for w in write_ups
        if w.reported.at <= t
    ]

    assert _grounding(status_at(write_ups, t)) == _grounding(status_at(known_then, t))
