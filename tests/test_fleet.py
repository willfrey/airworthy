"""An aircraft is grounded exactly while one of its write-ups is open and high."""

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Final

import pytest
from hypothesis import given, strategies as st

from airworthy.fleet import Cleared, Grounded, status_at
from airworthy.writeup import (
    Closed,
    Open,
    Reclassified,
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


def _reclassified(severity: Severity, minutes: int) -> Reclassified:
    return Reclassified(
        at=_at(minutes), by="Lin Zhou", severity=severity, reason="Measured the crack"
    )


def _resolved(minutes: int) -> Resolved:
    return Resolved(at=_at(minutes), by="Sam Okafor", note="Replaced the pane")


def _reopened(minutes: int) -> Reopened:
    return Reopened(at=_at(minutes), by="Ana Reyes", reason="Crack is back")


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


def test_a_past_answer_names_the_write_up_as_it_was_known_then() -> None:
    """Asked about minute 5, the answer must not carry the resolve of minute 10."""
    fixed_later = _write_up(1, Severity.HIGH, _resolved(10))

    status = status_at([fixed_later], _at(5))

    assert status == Grounded(by=(_write_up(1, Severity.HIGH),))


def test_a_high_lowered_while_resolved_does_not_ground_when_reopened() -> None:
    log = _write_up(
        1,
        Severity.HIGH,
        _resolved(5),
        _reclassified(Severity.MEDIUM, 10),
        _reopened(15),
    )

    assert status_at([log], _at(15)) == Cleared()


def test_a_low_raised_to_high_while_resolved_grounds_when_reopened() -> None:
    log = _write_up(
        1, Severity.LOW, _resolved(5), _reclassified(Severity.HIGH, 10), _reopened(15)
    )

    assert status_at([log], _at(14)) == Cleared()
    assert status_at([log], _at(15)) == Grounded(by=(log,))


# The laws, over generated histories. Each follow-up is drawn from the moves the
# transition table allows in the state reached so far, a few minutes after the last
# one or at the same instant, so `apply` refusing one fails the test.

_NAMES: Final = st.just("Sam Okafor")
_TEXTS: Final = st.just("Noted on the walk-round")
_SEVERITIES: Final = st.sampled_from(list(Severity))
_MOMENTS: Final = st.integers(-1, 40).map(_at)


def _moves(state: State, at: datetime) -> st.SearchStrategy[FollowUp]:
    """Give the follow-ups the table allows on a state, dated `at`."""
    moment = st.just(at)
    reclassified = st.builds(
        Reclassified, at=moment, by=_NAMES, severity=_SEVERITIES, reason=_TEXTS
    )
    match state:
        case Open():
            return st.one_of(
                reclassified,
                st.builds(
                    Scheduled, at=moment, by=_NAMES, on=st.just(date(2026, 1, 12))
                ),
                st.builds(Resolved, at=moment, by=_NAMES, note=_TEXTS),
            )
        case Closed():
            return st.one_of(
                reclassified, st.builds(Reopened, at=moment, by=_NAMES, reason=_TEXTS)
            )


@st.composite
def _histories(draw: st.DrawFn) -> list[WriteUp]:
    """Draw one aircraft's write-ups, each a log of allowed moves, with distinct ids."""
    write_ups: list[WriteUp] = []
    for number in range(draw(st.integers(0, 3))):
        minute = draw(st.integers(0, 10))
        reported = Reported(
            at=_at(minute), by="Ana Reyes", severity=draw(_SEVERITIES), description="x"
        )
        state: State = opened(reported)
        later: list[FollowUp] = []
        for _ in range(draw(st.integers(0, 8))):
            minute += draw(st.integers(0, 3))
            event = draw(_moves(state, _at(minute)))
            state = apply(state, event)
            later.append(event)
        write_ups.append(
            WriteUp(id=number, tail="N101AW", reported=reported, later=tuple(later))
        )
    return write_ups


def _cut_by_hand(write_up: WriteUp, t: datetime) -> WriteUp:
    return WriteUp(
        id=write_up.id,
        tail=write_up.tail,
        reported=write_up.reported,
        later=tuple(event for event in write_up.later if event.at <= t),
    )


# This calls neither `known_at`, `latest` nor `Severity.grounds`, so the property below
# compares the code with an answer the code did not help produce.
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


@given(write_ups=_histories(), t=_MOMENTS)
def test_an_aircraft_is_grounded_exactly_by_its_open_highs(
    write_ups: list[WriteUp], t: datetime
) -> None:
    expected = [w.id for w in write_ups if _grounds_by_hand(w, t)]

    assert _grounding(status_at(write_ups, t)) == expected


@given(write_ups=_histories(), t=_MOMENTS)
def test_events_after_a_moment_never_change_the_status_at_it(
    write_ups: list[WriteUp], t: datetime
) -> None:
    """A past view is trustworthy only if nothing recorded later can alter it.

    The whole answer is compared, the grounding write-ups' logs included, against the
    answer from logs cut by hand to what had been recorded by then.
    """
    known_then = [_cut_by_hand(w, t) for w in write_ups if w.reported.at <= t]

    assert status_at(write_ups, t) == status_at(known_then, t)
