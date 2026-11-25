"""A write-up: one reported defect on one aircraft, from report to repair.

A write-up is a log of events. A report opens it, and each follow-up moves it by one
rule, `apply`:

| Follow-up      | on an open write-up            | on a resolved write-up      |
|----------------|--------------------------------|-----------------------------|
| `Reclassified` | the new severity               | the new severity, resolved  |
| `Scheduled`    | the new date, replacing an old | refused                     |
| `Resolved`     | resolved                       | refused                     |
| `Reopened`     | refused                        | open, with no repair date   |

Nothing here stores a state: `latest` folds a log to its state, and `known_at` cuts a
log to what was known at a moment.
"""

from dataclasses import dataclass
from datetime import UTC, date
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal, assert_never

from pydantic import AwareDatetime, Field, StringConstraints

from airworthy.model import Model

if TYPE_CHECKING:
    from datetime import datetime

type Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""Text a person wrote: stripped, and never blank."""


class Severity(StrEnum):
    """How serious a defect is, as the person filing or correcting it judged."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def grounds(self) -> bool:
        """Whether an open write-up of this severity keeps its aircraft from flying."""
        match self:
            case Severity.HIGH:
                return True
            case Severity.MEDIUM | Severity.LOW:
                return False
            case unreachable:
                assert_never(unreachable)


class Event(Model):
    """Something a named person did to a write-up at a moment."""

    at: AwareDatetime
    by: Text


class Reported(Event):
    """The report that opens a write-up, at the severity its reporter chose."""

    kind: Literal["reported"] = "reported"
    severity: Severity
    description: Text


class Reclassified(Event):
    """A correction of the severity, with the reason for it.

    Lowering a high is the one way an aircraft is released without a repair, which is
    why the reason is required.
    """

    kind: Literal["reclassified"] = "reclassified"
    severity: Severity
    reason: Text


class Scheduled(Event):
    """A repair date, replacing any earlier one."""

    kind: Literal["scheduled"] = "scheduled"
    on: date


class Resolved(Event):
    """The repair, signed off by the person who did it."""

    kind: Literal["resolved"] = "resolved"
    note: Text


class Reopened(Event):
    """A resolved defect that came back: "resolved" is deliberately not forever."""

    kind: Literal["reopened"] = "reopened"
    reason: Text


type FollowUp = Annotated[
    Reclassified | Scheduled | Resolved | Reopened, Field(discriminator="kind")
]
"""An event on a write-up that its report already opened, told apart by `kind`."""


class WriteUp(Model):
    """A write-up's log: exactly one report, then its follow-ups in log order."""

    id: int
    tail: str
    reported: Reported
    later: tuple[FollowUp, ...] = ()


@dataclass(slots=True, kw_only=True, frozen=True)
class Open:
    """A write-up awaiting repair, with its repair date once it has one."""

    severity: Severity
    scheduled_for: date | None
    as_of: datetime
    """When the last event applied happened."""


@dataclass(slots=True, kw_only=True, frozen=True)
class Closed:
    """A resolved write-up: when it was repaired, by whom, and their note."""

    severity: Severity
    at: datetime
    by: str
    note: str
    as_of: datetime
    """When the last event applied happened: past `at` after a later correction."""


type State = Open | Closed


class RefusedError(Exception):
    """A follow-up the write-up's state doesn't allow; its text is for the person."""


def opened(reported: Reported) -> Open:
    """Give the state a report opens: unscheduled, at the reported severity."""
    return Open(severity=reported.severity, scheduled_for=None, as_of=reported.at)


def apply(state: State, event: FollowUp) -> State:
    """Give the state `event` moves `state` to, by the module's table.

    Args:
        state: The write-up's state before the event.
        event: The follow-up to apply.

    Returns:
        The state after the event.

    Raises:
        RefusedError: When the table refuses the event in this state, or the event is
            dated before the last one applied.
    """
    if event.at < state.as_of:
        msg = "an event can't be dated before the write-up's last event"
        raise RefusedError(msg)
    match state:
        case Open():
            return _on_open(state, event)
        case Closed():
            return _on_closed(state, event)
        case unreachable:
            assert_never(unreachable)


def _on_open(state: Open, event: FollowUp) -> State:
    match event:
        case Reclassified():
            return Open(
                severity=event.severity,
                scheduled_for=state.scheduled_for,
                as_of=event.at,
            )
        case Scheduled():
            return Open(severity=state.severity, scheduled_for=event.on, as_of=event.at)
        case Resolved():
            return Closed(
                severity=state.severity,
                at=event.at,
                by=event.by,
                note=event.note,
                as_of=event.at,
            )
        case Reopened():
            msg = "this write-up is already open"
            raise RefusedError(msg)
        case unreachable:
            assert_never(unreachable)


def _on_closed(state: Closed, event: FollowUp) -> State:
    match event:
        case Reclassified():
            return Closed(
                severity=event.severity,
                at=state.at,
                by=state.by,
                note=state.note,
                as_of=event.at,
            )
        case Scheduled():
            msg = "a resolved write-up can't be scheduled; reopen it first"
            raise RefusedError(msg)
        case Resolved():
            msg = "this write-up is already resolved"
            raise RefusedError(msg)
        case Reopened():
            return Open(severity=state.severity, scheduled_for=None, as_of=event.at)
        case unreachable:
            assert_never(unreachable)


def known_at(write_up: WriteUp, t: datetime) -> WriteUp | None:
    """Give a write-up as it was known at `t`: its log, cut off after that moment.

    Args:
        write_up: The whole log.
        t: The moment to read, which must carry a time zone.

    Returns:
        The write-up with only the follow-ups dated at or before `t`, in log order, or
        `None` when `t` is before the report. The whole log is checked whatever `t`
        is: one holding a follow-up that `apply` refuses fails with that refusal at
        every moment read, and no log written through `apply` holds one.
    """
    _ = latest(write_up)
    if t < write_up.reported.at:
        return None
    return WriteUp(
        id=write_up.id,
        tail=write_up.tail,
        reported=write_up.reported,
        later=tuple(event for event in write_up.later if event.at <= t),
    )


def latest(write_up: WriteUp) -> State:
    """Fold a write-up's whole log to its state after the last event."""
    state: State = opened(write_up.reported)
    for event in write_up.later:
        state = apply(state, event)
    return state


def needs_scheduling(state: State) -> bool:
    """Tell whether a write-up is open with no repair date."""
    return isinstance(state, Open) and state.scheduled_for is None


def overdue(state: State, moment: datetime) -> bool:
    """Tell whether a write-up is open with a repair date before `moment`'s UTC day."""
    return (
        isinstance(state, Open)
        and state.scheduled_for is not None
        and state.scheduled_for < utc_day(moment)
    )


def utc_day(moment: datetime) -> date:
    """Give the UTC calendar day a moment falls on, the day a repair date is read by."""
    # The one mutant here swaps UTC for None, the machine's own zone: the same call
    # wherever that zone is UTC, as it is on CI.
    return moment.astimezone(UTC).date()  # pragma: no mutate — None is UTC on CI
