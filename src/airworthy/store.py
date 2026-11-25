"""The event store: the fleet and each write-up's log, kept in SQLite.

A write-up is stored as its events and nothing else. Each event is one row holding the
whole event as JSON, in the order it was recorded, so there is no stored state, kind or
time column to fall out of step with the log.

A follow-up is checked against the log and recorded inside one write transaction that
is taken before anything is read, so two people acting on one write-up at once are
checked one after the other, the second against what the first recorded.
"""

import json
import sqlite3
from contextlib import closing, contextmanager
from typing import TYPE_CHECKING, Final, Self, cast

from airworthy.fleet import Aircraft
from airworthy.writeup import WriteUp, apply, latest

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    from airworthy.writeup import FollowUp, Reported

type Connect = Callable[[], sqlite3.Connection]
"""Opens a new connection to the store's database."""

SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS aircraft (
    tail TEXT PRIMARY KEY,
    type TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS write_ups (
    id INTEGER PRIMARY KEY,
    tail TEXT NOT NULL REFERENCES aircraft (tail)
) STRICT;
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY,
    write_up_id INTEGER NOT NULL REFERENCES write_ups (id),
    body TEXT NOT NULL
) STRICT;
"""
# SQLite ignores REFERENCES on a connection that hasn't turned this on.
FOREIGN_KEYS_ON: Final = "PRAGMA foreign_keys = ON"
# IMMEDIATE takes the write lock at once, where a plain BEGIN waits for the first write.
BEGIN_WRITE: Final = "BEGIN IMMEDIATE"
COMMIT: Final = "COMMIT"
INSERT_AIRCRAFT: Final = "INSERT INTO aircraft (tail, type) VALUES (?, ?)"
SELECT_AIRCRAFT: Final = """
SELECT tail, type FROM aircraft WHERE ?1 IS NULL OR tail = ?1 ORDER BY tail
"""
INSERT_WRITE_UP: Final = "INSERT INTO write_ups (tail) VALUES (?) RETURNING id"
INSERT_EVENT: Final = "INSERT INTO events (write_up_id, body) VALUES (?, ?)"
SELECT_LOGS: Final = """
SELECT write_ups.id, write_ups.tail, events.body
FROM write_ups JOIN events ON events.write_up_id = write_ups.id
WHERE (?1 IS NULL OR write_ups.tail = ?1) AND (?2 IS NULL OR write_ups.id = ?2)
ORDER BY write_ups.id, events.seq
"""


class NotFoundError(Exception):
    """An aircraft or a write-up the store doesn't hold; its text is for the person."""


class Store:
    """The fleet's aircraft and write-up logs in one SQLite database."""

    def __init__(self, connect: Connect) -> None:
        """Keep the way to reach the database, and make its tables if it has none.

        Args:
            connect: Opens a new connection. Each call of a method opens one and
                closes it, since a connection can't leave the thread that opened it.
        """
        self._connect = connect
        with self._connection() as connection:
            _ = connection.executescript(SCHEMA)

    @classmethod
    def at(cls, path: Path) -> Self:
        """Give a store whose database is the file at `path`, made if it is missing."""

        def connect() -> sqlite3.Connection:
            return sqlite3.connect(path)

        return cls(connect)

    def add_aircraft(self, aircraft: Aircraft) -> None:
        """Add an aircraft to the fleet."""
        with self._writing() as connection:
            _ = connection.execute(INSERT_AIRCRAFT, (aircraft.tail, aircraft.type))

    def all_aircraft(self) -> list[Aircraft]:
        """Give every aircraft in the fleet, in tail-number order."""
        return self._fleet(None)

    def aircraft(self, tail: str) -> Aircraft:
        """Give the aircraft with a tail number, or fail with `NotFoundError`."""
        match self._fleet(tail):
            case [aircraft]:
                return aircraft
            case _:
                raise NotFoundError(_no_aircraft(tail))

    def file(self, tail: str, reported: Reported) -> int:
        """Open a write-up on an aircraft with its report.

        Args:
            tail: The aircraft's tail number.
            reported: The report that opens the write-up.

        Returns:
            The new write-up's id.

        Raises:
            NotFoundError: When the fleet has no aircraft with that tail number.
        """
        with self._writing() as connection:
            try:
                row = cast(
                    "tuple[int]",
                    connection.execute(INSERT_WRITE_UP, (tail,)).fetchone(),
                )
            except sqlite3.IntegrityError as error:
                raise NotFoundError(_no_aircraft(tail)) from error
            _ = connection.execute(INSERT_EVENT, (row[0], reported.model_dump_json()))
        return row[0]

    def append(self, write_up_id: int, follow_up: FollowUp) -> None:
        """Record a follow-up on a write-up, if its log allows it.

        The write-up's log is read and checked only once this call holds the
        database's write lock, so no other follow-up can land between the check and
        the record. A follow-up the write-up's state doesn't allow fails with the
        refusal `apply` gives, and an id no write-up has with `NotFoundError`; either
        way nothing is recorded.

        Args:
            write_up_id: The write-up to follow up.
            follow_up: The event to record.
        """
        with self._writing() as connection:
            _ = apply(latest(_one(connection, write_up_id)), follow_up)
            body = follow_up.model_dump_json()
            _ = connection.execute(INSERT_EVENT, (write_up_id, body))

    def write_up(self, write_up_id: int) -> WriteUp:
        """Give the write-up with an id, or fail with `NotFoundError`."""
        with self._connection() as connection:
            return _one(connection, write_up_id)

    def write_ups(self, tail: str | None = None) -> list[WriteUp]:
        """Give one aircraft's write-ups, or the whole fleet's, in the order filed."""
        with self._connection() as connection:
            return _logs(connection, tail=tail)

    def _fleet(self, tail: str | None) -> list[Aircraft]:
        with self._connection() as connection:
            rows = cast(
                "list[tuple[str, str]]",
                connection.execute(SELECT_AIRCRAFT, (tail,)).fetchall(),
            )
        return [Aircraft(tail=found, type=kind) for found, kind in rows]

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection]:
        """Open a connection for one operation, and close it after."""
        with closing(self._connect()) as connection:
            # A connection opened with autocommit off is already inside a transaction,
            # where BEGIN_WRITE fails.
            connection.autocommit = True
            _ = connection.execute(FOREIGN_KEYS_ON)
            yield connection

    @contextmanager
    def _writing(self) -> Generator[sqlite3.Connection]:
        """Hold the write lock for one operation, committing only if it finishes."""
        with self._connection() as connection:
            _ = connection.execute(BEGIN_WRITE)
            # An operation that raises must not be committed: it leaves here with its
            # transaction open, and the connection closing rolls that back.
            yield connection  # ruff: ignore[fallible-context-manager] — as above
            _ = connection.execute(COMMIT)


def _no_aircraft(tail: str) -> str:
    return f"no aircraft {tail}"


def _one(connection: sqlite3.Connection, write_up_id: int) -> WriteUp:
    match _logs(connection, write_up_id=write_up_id):
        case [write_up]:
            return write_up
        case _:
            msg = f"no write-up {write_up_id}"
            raise NotFoundError(msg)


def _logs(
    connection: sqlite3.Connection,
    *,
    tail: str | None = None,
    write_up_id: int | None = None,
) -> list[WriteUp]:
    """Read the logs that match, each validated back into its events."""
    rows = cast(
        "list[tuple[int, str, str]]",
        connection.execute(SELECT_LOGS, (tail, write_up_id)).fetchall(),
    )
    logs: dict[tuple[int, str], list[str]] = {}
    for number, on, body in rows:
        logs.setdefault((number, on), []).append(body)
    return [_write_up(number, on, bodies) for (number, on), bodies in logs.items()]


def _write_up(number: int, tail: str, bodies: list[str]) -> WriteUp:
    reported, *later = (_event(body) for body in bodies)
    log: dict[str, object] = {
        "id": number,
        "tail": tail,
        "reported": reported,
        "later": later,
    }
    return WriteUp.model_validate(log)


def _event(body: str) -> dict[str, object]:
    """Read one stored event as plain JSON, for the model to validate."""
    return cast("dict[str, object]", json.loads(body))
