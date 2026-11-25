"""Airworthiness: whether an aircraft is cleared to fly at a moment.

An aircraft is grounded exactly while it has an open write-up whose severity grounds.
The answer is worked out from the aircraft's write-ups each time it is asked, and is
stored nowhere.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import StringConstraints

from airworthy.model import Model
from airworthy.writeup import Open, known_at, latest

# Building a schema from `Grounded` reads its annotations at run time, so this name
# must exist then.
lazy from airworthy.writeup import WriteUp

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime


class Aircraft(Model):
    """One aircraft in the fleet, known by its tail number."""

    tail: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9-]+$")]
    """Capitals, digits and hyphens only, so a tail is safe as a piece of a URL."""
    type: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Cleared:
    """An aircraft that no open write-up grounds."""

    kind: Literal["cleared"] = "cleared"
    """Names the status where it is written out: without it this is an empty record."""


@dataclass(slots=True, kw_only=True, frozen=True)
class Grounded:
    """An aircraft that may not fly, and the write-ups that say so."""

    by: tuple[WriteUp, *tuple[WriteUp, ...]]
    """Every open write-up that grounds the aircraft, in the order given.

    Each is the write-up as it was known at the moment asked about, so a past answer
    holds nothing recorded later.
    """
    kind: Literal["grounded"] = "grounded"
    """Names the status where it is written out."""


type Status = Cleared | Grounded


def status_at(write_ups: Iterable[WriteUp], t: datetime) -> Status:
    """Tell whether an aircraft with these write-ups is cleared to fly at `t`.

    Args:
        write_ups: Every write-up on the one aircraft.
        t: The moment to read, which must carry a time zone.

    Returns:
        `Grounded` by each write-up that is open at `t` with a severity that grounds,
        each cut to what was known at `t`, or `Cleared` when there is none.
    """
    known = (known_at(write_up, t) for write_up in write_ups)
    match [
        write_up for write_up in known if write_up is not None and _grounds(write_up)
    ]:
        case [first, *rest]:
            return Grounded(by=(first, *rest))
        case _:
            return Cleared()


def _grounds(write_up: WriteUp) -> bool:
    state = latest(write_up)
    return isinstance(state, Open) and state.severity.grounds
