"""Severity triage: a suggested severity for a defect, from its description.

A suggestion informs the person filing a write-up and decides nothing: the severity
that can ground an aircraft is the one that person picks. This module only asks a
model and hands back what it said.
"""

import asyncio
from contextlib import closing
from typing import TYPE_CHECKING, Final

from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, UserError

from airworthy.writeup import Severity, Suggestion

if TYPE_CHECKING:
    from collections.abc import Callable

MODEL: Final = "anthropic:claude-opus-5-5"
TASK: Final = (
    "You help a person file an aircraft maintenance write-up. Given their description"
    " of a defect, suggest its severity."
)
RULE: Final = (
    "When the description leaves the choice open, suggest the higher severity. Give a"
    " short reason that names anything that would change the severity. The person"
    " makes the final choice, so write the reason for them."
)


def instructions() -> str:
    """Give the model its task, with what each severity means as `Severity` says it."""
    meanings = "\n".join(f"- {severity}: {severity.meaning}" for severity in Severity)
    return f"{TASK}\n\n{meanings}\n\n{RULE}"


agent: Final = Agent(
    MODEL, output_type=Suggestion, instructions=instructions, defer_model_check=True
)
"""The agent `suggest` runs; a test overrides its model."""

type Suggester = Callable[[str], Suggestion]
"""Suggests a severity for a description, or raises `NoSuggestionError`."""


class NoSuggestionError(Exception):
    """The model gave no suggestion; its text is for the person."""


def suggest(description: str) -> Suggestion:
    """Ask the model for a severity for `description`.

    Args:
        description: What the person wrote about the defect.

    Returns:
        The severity the model suggests, with its reason.

    Raises:
        NoSuggestionError: When the model can't be reached or isn't set up (no key,
            say), refuses, or answers with something that isn't a suggestion.
    """
    # `run_sync` leaves the event loop it runs on open, and on a request's worker
    # thread nothing else closes it, so the loop is made and closed here.
    with closing(asyncio.new_event_loop()) as loop:
        asyncio.set_event_loop(loop)
        try:
            return agent.run_sync(description).output
        except (AgentRunError, UserError) as error:
            msg = "the model gave no suggestion; choose a severity yourself"
            raise NoSuggestionError(msg) from error
