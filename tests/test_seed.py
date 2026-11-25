"""The sample fleet loads with each aircraft's story intact, whenever it is loaded."""

from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Final

import pytest

from airworthy import seed
from airworthy.fleet import Aircraft, Cleared, Grounded, status_at
from airworthy.store import Store
from airworthy.writeup import Open, latest, needs_scheduling, overdue

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit

# 07:30 UTC on 3 March, told in a zone where it is still 2 March. Before 12:00 UTC, the
# time of day the seed's anchor has, the whole days between the anchor and this moment
# are one fewer than the days between their two UTC dates; and in this zone the local
# date is not the UTC date, so a repair date moved by either is a day out.
NOW: Final = datetime(2026, 3, 2, 23, 30, tzinfo=timezone(timedelta(hours=-8)))


@pytest.fixture
def store(tmp_path: Path) -> Store:
    """Give a store holding the sample fleet, loaded as of `NOW`."""
    made = Store.at(tmp_path / "fleet.db")
    seed.load(made, NOW)
    return made


def _grounding(store: Store, at: datetime) -> dict[str, list[int]]:
    """Give, for each aircraft, the ids of the write-ups grounding it at a moment."""
    grounding: dict[str, list[int]] = {}
    for aircraft in store.all_aircraft():
        match status_at(store.write_ups(aircraft.tail), at):
            case Grounded(by=by):
                grounding[aircraft.tail] = [write_up.id for write_up in by]
            case Cleared():
                grounding[aircraft.tail] = []
    return grounding


def test_the_sample_fleet_has_six_aircraft(store: Store) -> None:
    assert store.all_aircraft() == [
        Aircraft(tail="N101AW", type="Airbus A320"),
        Aircraft(tail="N102AW", type="Airbus A320"),
        Aircraft(tail="N103AW", type="Boeing 737-800"),
        Aircraft(tail="N104AW", type="Embraer E175"),
        Aircraft(tail="N105AW", type="Embraer E175"),
        Aircraft(tail="N106AW", type="ATR 72-600"),
    ]


def test_the_sample_fleet_shows_every_status_now(store: Store) -> None:
    assert _grounding(store, NOW) == {
        "N101AW": [],
        "N102AW": [2],
        "N103AW": [],
        "N104AW": [5, 6],
        "N105AW": [7],
        "N106AW": [8],
    }


def test_the_sample_fleet_was_different_two_days_earlier(store: Store) -> None:
    assert _grounding(store, NOW - timedelta(days=2)) == {
        "N101AW": [],
        "N102AW": [],
        "N103AW": [3],
        "N104AW": [5, 6],
        "N105AW": [],
        "N106AW": [],
    }


def test_the_sample_fleet_has_two_write_ups_waiting_for_a_repair_date(
    store: Store,
) -> None:
    waiting = [w.id for w in store.write_ups() if needs_scheduling(latest(w))]

    assert waiting == [6, 8]


def test_the_sample_fleet_has_one_overdue_repair(store: Store) -> None:
    late = [w.id for w in store.write_ups() if overdue(latest(w), NOW)]

    assert late == [4]


def test_a_repair_set_for_the_day_after_the_anchor_is_set_for_tomorrow(
    store: Store,
) -> None:
    [cracked_windshield] = store.write_ups("N102AW")

    state = latest(cracked_windshield)

    assert isinstance(state, Open)
    assert state.scheduled_for == date(2026, 3, 4)
    assert state.as_of == NOW - timedelta(hours=2, minutes=20)
