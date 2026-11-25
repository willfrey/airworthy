"""The web app: the fleet board, each aircraft's page, and the forms that act.

A page is rendered on the server from the store at each request, so what it shows is
what the logs say at that moment. No rule is decided here: a form is turned into an
event, the store accepts or refuses it, and a refusal is shown to the person as the
domain worded it.

A page takes an `at` to show the fleet as it stood at a past moment. A past view has no
forms: an action is always taken now, by the server's clock.
"""

import argparse
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final, Protocol, assert_never

import uvicorn
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, PackageLoader
from pydantic import ValidationError

from airworthy import seed
from airworthy.fleet import Cleared, Grounded, status_at
from airworthy.model import Model, faults
from airworthy.store import NotFoundError, Store
from airworthy.writeup import (
    FollowUp,
    RefusedError,
    Reported,
    known_at,
    latest,
    standing,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from fastapi import Request

    from airworthy.fleet import Aircraft, Status
    from airworthy.writeup import Standing, State, WriteUp

ENVIRONMENT: Final = Environment(loader=PackageLoader("airworthy"), autoescape=True)
BOARD: Final = "board.html"
AIRCRAFT: Final = "aircraft.html"
PROBLEM: Final = "problem.html"
POST: Final = ["POST"]
STAMP: Final = "%Y-%m-%d %H:%M UTC"
DATABASE: Final = "airworthy.db"

type Clock = Callable[[], datetime]
"""Tells the moment an action is taken; it must carry a time zone."""


class ActionForm(Model):
    """What a form posts: text for whichever fields its action has."""

    kind: str | None = None
    by: str | None = None
    severity: str | None = None
    description: str | None = None
    reason: str | None = None
    on: str | None = None
    note: str | None = None


class Action(Model):
    """A follow-up as a form posted it, its `kind` saying which one."""

    event: FollowUp


class NotATimeError(Exception):
    """An `at` that can't be read as a moment; its text is for the person."""


@dataclass(slots=True, kw_only=True, frozen=True)
class Entry:
    """One write-up as it was known at a moment, and where it stood then."""

    write_up: WriteUp
    state: State
    standing: Standing


@dataclass(slots=True, kw_only=True, frozen=True)
class Row:
    """One aircraft at a moment: what grounds it, if anything, and its write-ups."""

    aircraft: Aircraft
    grounding: tuple[WriteUp, ...]
    entries: tuple[Entry, ...]


class Serve(Protocol):
    """Serves an app on a port until stopped, as `uvicorn.run` does."""

    def __call__(self, app: FastAPI, *, port: int) -> None:
        """Serve `app` on `port`."""


class Options(argparse.Namespace):
    """The command line's options, with their defaults."""

    port: int = 8000
    db: Path | None = None


def create_app(store: Store, clock: Clock) -> FastAPI:
    """Build the app over a store, taking the time of each action from `clock`."""
    app = FastAPI()

    def board(at: str = "") -> HTMLResponse:
        moment = _moment(at, clock())
        rows = [_row(store, aircraft, moment) for aircraft in store.all_aircraft()]
        return _page(BOARD, at=at, moment=moment, rows=rows)

    def aircraft(tail: str, at: str = "") -> HTMLResponse:
        return _aircraft(store, tail, _moment(at, clock()), at=at)

    def file(
        tail: str, form: Annotated[ActionForm, Form()]
    ) -> HTMLResponse | RedirectResponse:
        now = clock()
        fields = {**form.posted(), "at": now}
        try:
            reported = Reported.model_validate(fields)
        except ValidationError as error:
            return _aircraft(store, tail, now, problem=_problems(error))
        _ = store.file(tail, reported)
        return _back(tail)

    def follow_up(
        write_up_id: int, form: Annotated[ActionForm, Form()]
    ) -> HTMLResponse | RedirectResponse:
        now = clock()
        tail = store.write_up(write_up_id).tail
        fields = {"event": {**form.posted(), "at": now}}
        try:
            store.append(write_up_id, Action.model_validate(fields).event)
        except ValidationError as error:
            return _aircraft(store, tail, now, problem=_problems(error))
        except RefusedError as error:
            return _aircraft(store, tail, now, problem=str(error))
        return _back(tail)

    app.add_api_route("/", board)
    app.add_api_route("/aircraft/{tail}", aircraft)
    app.add_api_route(
        "/aircraft/{tail}/write-ups", file, methods=POST, response_model=None
    )
    app.add_api_route(
        "/write-ups/{write_up_id}/events", follow_up, methods=POST, response_model=None
    )
    app.add_exception_handler(NotFoundError, _not_found)
    app.add_exception_handler(NotATimeError, _not_a_time)
    return app


def main(argv: Sequence[str] | None = None, serve: Serve = uvicorn.run) -> None:
    """Serve the app, on a fresh copy of the sample fleet unless told otherwise.

    Args:
        argv: The command line's arguments: `--port`, and `--db` for a database file
            to keep between runs, which gets the sample fleet only while it holds no
            aircraft.
        serve: Serves the app; a test passes one that returns.
    """
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--port", type=int)
    _ = parser.add_argument("--db", type=Path)
    options = parser.parse_args(argv, namespace=Options())
    # A file in a new directory, not `:memory:`: every connection to that gets an
    # empty database of its own, and the store opens one per call.
    database = options.db or Path(tempfile.mkdtemp()) / DATABASE
    database.parent.mkdir(parents=True, exist_ok=True)
    store = Store.at(database)
    if not store.all_aircraft():
        seed.load(store, _now())
    serve(create_app(store, _now), port=options.port)


def _now() -> datetime:
    return datetime.now(UTC)


def _moment(at: str, now: datetime) -> datetime:
    """Read a page's `at` as a moment: blank is now, and a time with no zone is UTC."""
    if not at:
        return now
    try:
        moment = datetime.fromisoformat(at)
    except ValueError as error:
        msg = f"{at} isn't a time such as 2026-01-15T12:00"
        raise NotATimeError(msg) from error
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def _row(store: Store, aircraft: Aircraft, moment: datetime) -> Row:
    logs = (known_at(log, moment) for log in store.write_ups(aircraft.tail))
    known = [log for log in logs if log is not None]
    return Row(
        aircraft=aircraft,
        grounding=_grounding(status_at(known, moment)),
        entries=tuple(_entry(write_up, moment) for write_up in known),
    )


def _entry(write_up: WriteUp, moment: datetime) -> Entry:
    state = latest(write_up)
    return Entry(write_up=write_up, state=state, standing=standing(state, moment))


def _grounding(status: Status) -> tuple[WriteUp, ...]:
    match status:
        case Grounded(by=by):
            return by
        case Cleared():
            return ()
        case unreachable:
            assert_never(unreachable)


def _aircraft(
    store: Store,
    tail: str,
    moment: datetime,
    *,
    at: str = "",
    problem: str | None = None,
) -> HTMLResponse:
    """Render an aircraft's page, as a bad request when it carries a problem."""
    row = _row(store, store.aircraft(tail), moment)
    status = HTTPStatus.OK if problem is None else HTTPStatus.BAD_REQUEST
    return _page(AIRCRAFT, status, at=at, moment=moment, row=row, problem=problem)


def _page(
    name: str, status: HTTPStatus = HTTPStatus.OK, **context: object
) -> HTMLResponse:
    html = ENVIRONMENT.get_template(name).render(stamp=_stamp, **context)
    return HTMLResponse(html, status_code=status)


def _back(tail: str) -> RedirectResponse:
    return RedirectResponse(f"/aircraft/{tail}", status_code=HTTPStatus.SEE_OTHER)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(STAMP)


def _problems(error: ValidationError) -> str:
    """Say what a form got wrong, one field after another."""
    return "; ".join(f"{fault['loc'][-1]}: {fault['msg']}" for fault in faults(error))


def _not_found(_: Request, error: Exception) -> HTMLResponse:
    return _page(PROBLEM, HTTPStatus.NOT_FOUND, problem=str(error))


def _not_a_time(_: Request, error: Exception) -> HTMLResponse:
    return _page(PROBLEM, HTTPStatus.BAD_REQUEST, problem=str(error))
