"""Airworthiness: whether an aircraft is cleared to fly at a moment.

An aircraft is grounded exactly while it has an open write-up whose severity grounds.
The answer is worked out from the aircraft's write-ups each time it is asked, and is
stored nowhere.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from airworthy.writeup import Open, state_at

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from airworthy.writeup import WriteUp


@dataclass(slots=True, kw_only=True, frozen=True)
class Cleared:
    """An aircraft that no open write-up grounds."""


@dataclass(slots=True, kw_only=True, frozen=True)
class Grounded:
    """An aircraft that may not fly, and the write-ups that say so."""

    by: tuple[WriteUp, *tuple[WriteUp, ...]]
    """Every open write-up that grounds the aircraft, in the order given."""


type Status = Cleared | Grounded


def status_at(write_ups: Iterable[WriteUp], t: datetime) -> Status:
    """Tell whether an aircraft with these write-ups is cleared to fly at `t`.

    Args:
        write_ups: Every write-up on the one aircraft.
        t: The moment to read, which must carry a time zone.

    Returns:
        `Grounded` by each write-up that is open at `t` with a severity that grounds,
        or `Cleared` when there is none.
    """
    match [write_up for write_up in write_ups if _grounds_at(write_up, t)]:
        case [first, *rest]:
            return Grounded(by=(first, *rest))
        case _:
            return Cleared()


def _grounds_at(write_up: WriteUp, t: datetime) -> bool:
    state = state_at(write_up, t)
    return isinstance(state, Open) and state.severity.grounds
