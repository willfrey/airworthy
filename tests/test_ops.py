"""An answer is what the model said after reading through the tools, or a refusal."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from pydantic_ai.exceptions import ModelHTTPError, UserError
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from airworthy import ops
from airworthy.fleet import Aircraft, Cleared, Grounded
from airworthy.writeup import Closed, Reported, Severity, WriteUp, opened

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo


pytestmark = pytest.mark.unit

NOW = datetime(2026, 3, 3, 7, 30, tzinfo=UTC)
EARLIER = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
CRACK = WriteUp(
    id=2,
    tail="N102AW",
    reported=Reported(
        at=NOW, by="Ana Reyes", severity=Severity.HIGH, description="Cracked pane"
    ),
)
REPAIRED = Closed(
    severity=Severity.HIGH, at=NOW, by="Sam Okafor", note="Replaced the pane", as_of=NOW
)
CALLS = (
    ToolCallPart(tool_name="current_time", args={}),
    ToolCallPart(tool_name="fleet_status", args={"at": "2026-03-01T12:00:00Z"}),
    ToolCallPart(tool_name="fleet_status", args={}),
    ToolCallPart(tool_name="write_ups", args={"tail": "N102AW"}),
)


def _now() -> datetime:
    return NOW


class _Fleet:
    """Fake reads that keep what each was called with."""

    def __init__(self) -> None:
        self.moments: list[datetime | None] = []
        self.tails: list[str] = []
        self.reads = ops.Reads(now=_now, fleet=self.fleet, write_ups=self.logs)

    def fleet(self, at: datetime | None) -> tuple[ops.Listed, ...]:
        self.moments.append(at)
        flying = Aircraft(tail="N101AW", type="Airbus A320")
        held = Aircraft(tail="N102AW", type="Airbus A320")
        return (
            ops.Listed(aircraft=flying, status=Cleared()),
            ops.Listed(aircraft=held, status=Grounded(by=(CRACK,))),
        )

    def logs(self, tail: str) -> tuple[ops.Filed, ...] | None:
        self.tails.append(tail)
        return (
            ops.Filed(write_up=CRACK, state=opened(CRACK.reported)),
            ops.Filed(write_up=CRACK, state=REPAIRED),
        )


def _read_then_answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Call each tool in turn, then answer with what was asked and what came back."""
    parts = [part for message in messages for part in message.parts]
    returned = [part for part in parts if isinstance(part, ToolReturnPart)]
    if len(returned) < len(CALLS):
        return ModelResponse(parts=[CALLS[len(returned)]])
    asked = [part.content for part in parts if isinstance(part, UserPromptPart)]
    told = [f"{part.tool_name}={type(part.content).__name__}" for part in returned]
    read = " ".join(part.model_response_str() for part in returned)
    text = f"{asked} {told} {info.instructions} READ {read}"
    return ModelResponse(parts=[TextPart(text)])


def test_an_answer_comes_from_the_question_and_what_each_tool_read() -> None:
    fleet = _Fleet()

    with ops.agent.override(model=FunctionModel(_read_then_answer)):
        answer = ops.ask("Which aircraft can fly?", fleet.reads)

    assert answer.startswith(
        "['Which aircraft can fly?'] ['current_time=datetime', 'fleet_status=tuple',"
        " 'fleet_status=tuple', 'write_ups=tuple'] You answer a question about a"
        " fleet of aircraft and their maintenance write-ups, using only what the tools"
        " return."
    )
    read = answer.split(" READ ")[1]
    assert '"tail":"N101AW","type":"Airbus A320"},"status":{"kind":"cleared"}' in read
    assert '"kind":"grounded"' in read
    assert '"scheduled_for":null,"as_of":"2026-03-03T07:30:00Z","kind":"open"' in read
    assert (
        '"note":"Replaced the pane","as_of":"2026-03-03T07:30:00Z","kind":"resolved"'
        in read
    )
    assert fleet.moments == [EARLIER, None]
    assert fleet.tails == ["N102AW"]


@pytest.mark.parametrize(
    "error",
    [
        ModelHTTPError(529, "claude-opus-5-5"),
        UserError("Set the ANTHROPIC_API_KEY environment variable"),
    ],
)
def test_a_model_that_fails_or_is_not_set_up_gives_no_answer(
    error: Exception,
) -> None:
    def fail(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise error

    with (
        ops.agent.override(model=FunctionModel(fail)),
        pytest.raises(ops.NoAnswerError) as refused,
    ):
        _ = ops.ask("Which aircraft can fly?", _Fleet().reads)

    assert str(refused.value) == "the model gave no answer; the board is the record"


def test_asking_on_a_worker_thread_leaves_no_event_loop_open() -> None:
    """A request runs on a worker thread, where nothing else would close the loop."""

    def ask_then_look() -> bool:
        model = TestModel(call_tools=[], custom_output_text="All six.")
        with ops.agent.override(model=model):
            _ = ops.ask("Which aircraft can fly?", _Fleet().reads)
        return asyncio.get_event_loop().is_closed()

    with ThreadPoolExecutor(max_workers=1) as worker:
        assert worker.submit(ask_then_look).result()
