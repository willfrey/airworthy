"""A suggestion is what the model answered about a description, or a clear refusal."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest
from pydantic_ai.exceptions import ModelHTTPError, UserError
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from airworthy import triage
from airworthy.writeup import Severity, Suggestion

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

pytestmark = pytest.mark.unit

ANSWER = {"severity": "high", "reason": "Fluid under a gear can be a brake line leak"}
INSTRUCTIONS = """\
You help a person file an aircraft maintenance write-up. Given their description of a \
defect, suggest its severity.

- high: the aircraft should not fly until this is repaired. Choose it when the defect \
could affect the safety of a flight: structure, flight controls, engines, fuel, \
landing gear, pressurization, fire protection, or instruments and systems a flight \
depends on.
- medium: the aircraft can fly, and the repair should be planned soon.
- low: cosmetic or a matter of comfort, with no effect on the safety of a flight.

When the description leaves the choice open, suggest the higher severity. Give a \
short reason that names anything that would change the severity. The person makes \
the final choice, so write the reason for them."""


def test_a_suggestion_is_the_severity_and_reason_the_model_answered() -> None:
    with triage.agent.override(model=TestModel(custom_output_args=ANSWER)):
        suggestion = triage.suggest("Fluid under the left main gear")

    assert suggestion == Suggestion(
        severity=Severity.HIGH, reason="Fluid under a gear can be a brake line leak"
    )


def test_the_model_is_given_the_instructions_and_the_description_alone() -> None:
    asked: list[tuple[str | None, list[object]]] = []

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompts = [
            part.content
            for message in messages
            for part in message.parts
            if isinstance(part, UserPromptPart)
        ]
        asked.append((info.instructions, [*prompts]))
        [tool] = info.output_tools
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=ANSWER)])

    with triage.agent.override(model=FunctionModel(answer)):
        _ = triage.suggest("Fluid under the left main gear")

    assert asked == [(INSTRUCTIONS, ["Fluid under the left main gear"])]


def test_a_model_that_can_not_be_reached_gives_no_suggestion() -> None:
    def fail(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(529, "claude-opus-5-5")

    with (
        triage.agent.override(model=FunctionModel(fail)),
        pytest.raises(triage.NoSuggestionError) as refused,
    ):
        _ = triage.suggest("Fluid under the left main gear")

    assert str(refused.value) == (
        "the model gave no suggestion; choose a severity yourself"
    )


def test_a_model_that_is_not_set_up_gives_no_suggestion() -> None:
    """pydantic-ai raises `UserError`, no `AgentRunError`, for a missing key."""

    def fail(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        msg = "Set the ANTHROPIC_API_KEY environment variable"
        raise UserError(msg)

    with (
        triage.agent.override(model=FunctionModel(fail)),
        pytest.raises(triage.NoSuggestionError),
    ):
        _ = triage.suggest("Fluid under the left main gear")


def test_an_answer_that_is_no_suggestion_gives_no_suggestion() -> None:
    wrong = {"severity": "extreme", "reason": "Fluid"}

    with (
        triage.agent.override(model=TestModel(custom_output_args=wrong)),
        pytest.raises(triage.NoSuggestionError),
    ):
        _ = triage.suggest("Fluid under the left main gear")


def test_suggesting_on_a_worker_thread_leaves_no_event_loop_open() -> None:
    """A request runs on a worker thread, where nothing else would close the loop."""

    def suggest_then_look() -> bool:
        with triage.agent.override(model=TestModel(custom_output_args=ANSWER)):
            _ = triage.suggest("Fluid under the left main gear")
        return asyncio.get_event_loop().is_closed()

    with ThreadPoolExecutor(max_workers=1) as worker:
        assert worker.submit(suggest_then_look).result()
