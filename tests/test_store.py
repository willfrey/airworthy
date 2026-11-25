"""The store keeps each write-up's log as recorded, and records only what it allows."""

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Final

import pytest

from airworthy.fleet import Aircraft
from airworthy.store import NotFoundError, Store
from airworthy.writeup import (
    Reclassified,
    RefusedError,
    Reopened,
    Reported,
    Resolved,
    Scheduled,
    Severity,
    WriteUp,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit

T0: Final = datetime(2026, 1, 10, 9, 0, tzinfo=UTC)
REPORTED: Final = Reported(
    at=T0, by="Ana Reyes", severity=Severity.HIGH, description="Cracked pane"
)


def _at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def _resolved(minutes: int) -> Resolved:
    return Resolved(at=_at(minutes), by="Sam Okafor", note="Replaced the pane")


@pytest.fixture
def database(tmp_path: Path) -> Path:
    """Give the path of a database file that doesn't exist yet."""
    return tmp_path / "fleet.db"


@pytest.fixture
def store(database: Path) -> Store:
    """Give a store with its tables created and two aircraft in the fleet."""
    made = Store.at(database)
    made.create()
    made.add_aircraft(Aircraft(tail="N102AW", type="Airbus A320"))
    made.add_aircraft(Aircraft(tail="N101AW", type="ATR 72-600"))
    return made


def test_the_fleet_is_listed_in_tail_number_order(store: Store) -> None:
    assert store.all_aircraft() == [
        Aircraft(tail="N101AW", type="ATR 72-600"),
        Aircraft(tail="N102AW", type="Airbus A320"),
    ]


def test_a_filed_write_up_is_read_back_with_its_report(store: Store) -> None:
    number = store.file("N101AW", REPORTED)

    assert store.write_ups("N101AW") == [
        WriteUp(id=number, tail="N101AW", reported=REPORTED)
    ]


def test_each_filed_write_up_gets_its_own_id(store: Store) -> None:
    first = store.file("N101AW", REPORTED)
    second = store.file("N101AW", REPORTED)

    assert [write_up.id for write_up in store.write_ups("N101AW")] == [first, second]
    assert first != second


def test_filing_on_an_unknown_aircraft_is_refused_and_records_nothing(
    store: Store,
) -> None:
    with pytest.raises(NotFoundError) as missing:
        _ = store.file("N999ZZ", REPORTED)

    assert str(missing.value) == "no aircraft N999ZZ"
    assert store.write_ups() == []


def test_every_kind_of_follow_up_is_read_back_equal_and_in_order(store: Store) -> None:
    """Dumping an event to its row and validating it back is the identity."""
    later = (
        Scheduled(at=_at(1), by="Dee Park", on=date(2026, 1, 12)),
        Reclassified(
            at=_at(2), by="Lin Zhou", severity=Severity.MEDIUM, reason="Within limits"
        ),
        _resolved(3),
        Reopened(at=_at(4), by="Ana Reyes", reason="Crack is back"),
    )
    number = store.file("N101AW", REPORTED)

    for follow_up in later:
        store.append(number, follow_up)

    assert store.write_ups("N101AW") == [
        WriteUp(id=number, tail="N101AW", reported=REPORTED, later=later)
    ]


def test_a_follow_up_on_an_unknown_write_up_is_refused(store: Store) -> None:
    with pytest.raises(NotFoundError) as missing:
        store.append(99, _resolved(1))

    assert str(missing.value) == "no write-up 99"


def test_resolving_twice_is_refused_and_recorded_once(store: Store) -> None:
    number = store.file("N101AW", REPORTED)
    store.append(number, _resolved(1))

    with pytest.raises(RefusedError):
        store.append(number, _resolved(2))

    assert store.write_ups("N101AW") == [
        WriteUp(id=number, tail="N101AW", reported=REPORTED, later=(_resolved(1),))
    ]


def test_a_follow_up_takes_the_write_lock_before_it_reads_the_log(
    store: Store, database: Path
) -> None:
    """The promise that makes a check against the log safe from a racing writer.

    Another connection holds the write lock. A follow-up must fail on taking the lock,
    having read nothing: one that read the log first would have checked a state the
    other writer was about to change. No threads, and no timing.
    """
    number = store.file("N101AW", REPORTED)
    statements: list[str] = []

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(database, timeout=0)
        connection.set_trace_callback(statements.append)
        return connection

    with closing(sqlite3.connect(database, autocommit=True)) as holder:
        _ = holder.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            Store(connect).append(number, _resolved(1))

    assert [statement for statement in statements if "SELECT" in statement] == []
    assert "BEGIN IMMEDIATE" in statements


def test_write_ups_are_read_for_one_aircraft_or_for_the_whole_fleet(
    store: Store,
) -> None:
    first = store.file("N101AW", REPORTED)
    second = store.file("N102AW", REPORTED)
    store.append(first, _resolved(1))

    assert [write_up.id for write_up in store.write_ups("N102AW")] == [second]
    assert [(w.id, w.tail, len(w.later)) for w in store.write_ups()] == [
        (first, "N101AW", 1),
        (second, "N102AW", 0),
    ]
