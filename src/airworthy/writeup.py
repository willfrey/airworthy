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

from dataclasses import dataclass, replace
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
    """How serious a defect is, as the person filing or correcting it judged.

    The members are listed from the most serious to the least, and `below` reads that
    order: a `StrEnum`'s own `<` is alphabetical, which puts medium above high.
    """

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

    def below(self, other: Severity) -> bool:
        """Tell whether this severity is less serious than `other`."""
        order = list(Severity)
        return order.index(self) > order.index(other)


class Suggestion(Model):
    """A severity a model suggested for a description, and its reason.

    It informs the person filing and decides nothing: `Reported.severity` is theirs.
    """

    severity: Severity
    reason: Text


class Event(Model):
    """Something a named person did to a write-up at a moment."""

    at: AwareDatetime
    by: Text


class Reported(Event):
    """The report that opens a write-up, at the severity its reporter chose.

    `suggested` records what a model suggested, when the reporter asked for it. It is
    kept beside the choice and never read as the severity.
    """

    kind: Literal["reported"] = "reported"
    severity: Severity
    description: Text
    suggested: Suggestion | None = None


class Kind(StrEnum):
    """The kinds of follow-up, in the order a page offers them.

    Each follow-up names its member as its `kind`, which is what its JSON holds.
    """

    SCHEDULED = "scheduled"
    RESOLVED = "resolved"
    REOPENED = "reopened"
    RECLASSIFIED = "reclassified"


class Reclassified(Event):
    """A correction of the severity, with the reason for it.

    Lowering a high is the one way an aircraft is released without a repair, which is
    why the reason is required.
    """

    kind: Literal[Kind.RECLASSIFIED] = Kind.RECLASSIFIED
    severity: Severity
    reason: Text


class Scheduled(Event):
    """A repair date, replacing any earlier one."""

    kind: Literal[Kind.SCHEDULED] = Kind.SCHEDULED
    on: date


class Resolved(Event):
    """The repair, signed off by the person who did it."""

    kind: Literal[Kind.RESOLVED] = Kind.RESOLVED
    note: Text


class Reopened(Event):
    """A resolved defect that came back: "resolved" is deliberately not forever."""

    kind: Literal[Kind.REOPENED] = Kind.REOPENED
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


def refusal(state: State, kind: Kind) -> str | None:
    """Say why the module's table refuses a kind of follow-up on a state.

    This is the table's one home: `apply` refuses by it, and `allowed` reads it.

    Returns:
        The refusal in words for the person, or `None` when the table allows the kind.
    """
    match state:
        case Open():
            return _refusal_on_open(kind)
        case Closed():
            return _refusal_on_closed(kind)
        case unreachable:
            assert_never(unreachable)


def _refusal_on_open(kind: Kind) -> str | None:
    match kind:
        case Kind.REOPENED:
            return "this write-up is already open"
        case Kind.RECLASSIFIED | Kind.SCHEDULED | Kind.RESOLVED:
            return None
        case unreachable:
            assert_never(unreachable)


def _refusal_on_closed(kind: Kind) -> str | None:
    match kind:
        case Kind.SCHEDULED:
            return "a resolved write-up can't be scheduled; reopen it first"
        case Kind.RESOLVED:
            return "this write-up is already resolved"
        case Kind.RECLASSIFIED | Kind.REOPENED:
            return None
        case unreachable:
            assert_never(unreachable)


def allowed(state: State) -> tuple[Kind, ...]:
    """Name the kinds of follow-up `apply` accepts on a state, in `Kind`'s order."""
    return tuple(kind for kind in Kind if refusal(state, kind) is None)


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
    refused = refusal(state, event.kind)
    if refused is not None:
        raise RefusedError(refused)
    # Past the table, each kind does one thing whatever the state it is allowed on.
    match event:
        case Reclassified():
            return replace(state, severity=event.severity, as_of=event.at)
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


@dataclass(slots=True, kw_only=True, frozen=True)
class Waiting:
    """An open write-up with no repair date."""


@dataclass(slots=True, kw_only=True, frozen=True)
class Due:
    """An open write-up whose repair date has not passed."""

    on: date


@dataclass(slots=True, kw_only=True, frozen=True)
class Overdue:
    """An open write-up whose repair date is before the moment's UTC day."""

    on: date


type Standing = Waiting | Due | Overdue | Closed
"""Where a write-up stands on its way to repair; a resolved one stands as its state."""


def standing(state: State, moment: datetime) -> Standing:
    """Tell where a write-up in `state` stands at `moment`."""
    if isinstance(state, Closed):
        return state
    on = state.scheduled_for
    if on is None:
        return Waiting()
    return Overdue(on=on) if on < utc_day(moment) else Due(on=on)


def downgraded(reported: Reported) -> bool:
    """Tell whether a report was filed below the severity a model suggested for it."""
    suggested = reported.suggested
    return suggested is not None and reported.severity.below(suggested.severity)


def utc_day(moment: datetime) -> date:
    """Give the UTC calendar day a moment falls on, the day a repair date is read by."""
    # The one mutant here swaps UTC for None, the machine's own zone: the same call
    # wherever that zone is UTC, as it is on CI.
    return moment.astimezone(UTC).date()  # pragma: no mutate — None is UTC on CI
