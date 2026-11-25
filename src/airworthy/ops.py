"""Fleet questions: a question in plain words, answered from the fleet's records.

A model answers by calling tools, and every tool is one of the calls in `Reads`, none
of which changes anything. The answer is text for a person to check against the board,
which stays the record.
"""

import asyncio
from contextlib import closing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

# pydantic-ai reads a tool's annotations when the agent is built, so these names must
# exist at run time though only annotations use them.
lazy from datetime import datetime

from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, UserError
lazy from pydantic import AwareDatetime
lazy from pydantic_ai import RunContext

lazy from airworthy.fleet import Aircraft, Status
lazy from airworthy.writeup import State, WriteUp

if TYPE_CHECKING:
    from collections.abc import Callable

MODEL: Final = "anthropic:claude-opus-5-5"
"""The model this agent runs on, chosen for it alone."""
INSTRUCTIONS: Final = (
    "You answer a question about a fleet of aircraft and their maintenance write-ups,"
    " using only what the tools return. An aircraft is grounded while it has an open"
    " high-severity write-up, and cleared to fly otherwise. For a question about a"
    " past time, call current_time first to turn words such as 'yesterday morning'"
    " into a moment, then give that moment to fleet_status. Name each aircraft by its"
    " tail and each write-up by its number. When the tools don't hold the answer, say"
    " so. Answer in two or three sentences of plain text."
)


@dataclass(slots=True, kw_only=True, frozen=True)
class Listed:
    """One aircraft and whether it could fly at the moment asked about."""

    aircraft: Aircraft
    status: Status


@dataclass(slots=True, kw_only=True, frozen=True)
class Filed:
    """One write-up: every event recorded on it, and the state they add up to."""

    write_up: WriteUp
    state: State


@dataclass(slots=True, kw_only=True, frozen=True)
class Reads:
    """Every call a question's tools may make: each one reads, and none can write."""

    now: Callable[[], datetime]
    fleet: Callable[[datetime | None], tuple[Listed, ...]]
    """Every aircraft's status at a moment, or now when given `None`."""
    write_ups: Callable[[str], tuple[Filed, ...] | None]
    """An aircraft's write-ups as they stand now, or `None` for no such tail."""


def current_time(ctx: RunContext[Reads]) -> datetime:
    """Give the present moment.

    Returns:
        The moment, with its time zone.
    """
    return ctx.deps.now()


def fleet_status(
    ctx: RunContext[Reads], at: AwareDatetime | None = None
) -> tuple[Listed, ...]:
    """List every aircraft as cleared or grounded, with the write-ups grounding it.

    Args:
        ctx: The run's context.
        at: A past moment to list the fleet at, with its time zone. Leave it out for
            the fleet as it is now.

    Returns:
        Each aircraft with its status: cleared, or grounded by the write-ups named.
    """
    return ctx.deps.fleet(at)


def write_ups(ctx: RunContext[Reads], tail: str) -> tuple[Filed, ...] | None:
    """Give one aircraft's write-ups as they stand now, each with its whole history.

    Args:
        ctx: The run's context.
        tail: The aircraft's tail number, such as N102AW.

    Returns:
        The write-ups, open and resolved, or nothing when no aircraft has that tail.
    """
    return ctx.deps.write_ups(tail)


TOOLS: Final = (current_time, fleet_status, write_ups)

agent: Final = Agent(
    MODEL,
    deps_type=Reads,
    tools=TOOLS,
    instructions=INSTRUCTIONS,
    defer_model_check=True,
)
"""The agent `ask` runs; a test overrides its model."""

type Ask = Callable[[str, Reads], str]
"""Answers a question from the reads it is given, or raises `NoAnswerError`."""


class NoAnswerError(Exception):
    """The model gave no answer; its text is for the person."""


def ask(question: str, reads: Reads) -> str:
    """Ask the model a question about the fleet, to answer from `reads` alone.

    Args:
        question: What the person asked, in their words.
        reads: The calls the model's tools may make.

    Returns:
        The model's answer, as text.

    Raises:
        NoAnswerError: When the model can't be reached or isn't set up, or gives no
            answer.
    """
    # `run_sync` leaves the event loop it runs on open, and on a request's worker
    # thread nothing else closes it, so the loop is made and closed here.
    with closing(asyncio.new_event_loop()) as loop:
        asyncio.set_event_loop(loop)
        try:
            return agent.run_sync(question, deps=reads).output
        except (AgentRunError, UserError) as error:
            msg = "the model gave no answer; the board is the record"
            raise NoAnswerError(msg) from error
