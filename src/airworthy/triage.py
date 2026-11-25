"""Severity triage: a suggested severity for a defect, from its description.

A suggestion informs the person filing a write-up and decides nothing: the severity
that can ground an aircraft is the one that person picks. This module only asks a
model and hands back what it said.
"""

import asyncio
from contextlib import closing
from typing import TYPE_CHECKING, Final

from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError

from airworthy.writeup import Suggestion

if TYPE_CHECKING:
    from collections.abc import Callable

MODEL: Final = "anthropic:claude-opus-5-5"
INSTRUCTIONS: Final = """\
You help a person file an aircraft maintenance write-up. Given their description of a
defect, suggest its severity.

- high: the aircraft should not fly until this is repaired. Choose it when the defect
  could affect the safety of a flight: structure, flight controls, engines, fuel,
  landing gear, pressurization, fire protection, or instruments and systems a flight
  depends on.
- medium: the aircraft can fly, and the repair should be planned soon.
- low: cosmetic or a matter of comfort, with no effect on the safety of a flight.

When the description leaves the choice open, suggest the higher severity. Give a short
reason that names anything that would change the severity. The person makes the final
choice, so write the reason for them.
"""

agent: Final = Agent(
    MODEL, output_type=Suggestion, instructions=INSTRUCTIONS, defer_model_check=True
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
        NoSuggestionError: When the model can't be reached, refuses, or answers with
            something that isn't a suggestion.
    """
    # `run_sync` leaves the event loop it runs on open, and on a request's worker
    # thread nothing else closes it, so the loop is made and closed here.
    with closing(asyncio.new_event_loop()) as loop:
        asyncio.set_event_loop(loop)
        try:
            return agent.run_sync(description).output
        except AgentRunError as error:
            msg = "the model gave no suggestion; choose a severity yourself"
            raise NoSuggestionError(msg) from error
