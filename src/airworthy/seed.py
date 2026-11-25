"""The sample fleet: six aircraft, one story each, loaded as if they just happened.

The stories are data, in `seed.json`, in the store's own event format. They are timed
around a fixed anchor and moved to end at the moment of loading, so a write-up
"reported three hours ago" is that whenever the app starts. Each event goes into the
store the way a person's action does, so a story that breaks a rule fails to load.
"""

from importlib.resources import files
from typing import TYPE_CHECKING, Final

from pydantic import AwareDatetime

from airworthy.fleet import Aircraft
from airworthy.model import Model
from airworthy.writeup import FollowUp, Reported, Scheduled, utc_day

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from airworthy.store import Store
    from airworthy.writeup import Event

SEED_FILE: Final = "seed.json"


class Log(Model):
    """One write-up's story: its aircraft, its report and what followed."""

    tail: str
    reported: Reported
    later: tuple[FollowUp, ...]


class Seed(Model):
    """The sample data, timed as if now were `anchor`."""

    anchor: AwareDatetime
    aircraft: tuple[Aircraft, ...]
    write_ups: tuple[Log, ...]


def load(store: Store, now: datetime) -> None:
    """Load the sample fleet into an empty store, its stories ending at `now`.

    Args:
        store: A store with its tables created and nothing in them.
        now: The moment the stories are told from, which must carry a time zone.
    """
    seed = Seed.model_validate_json(files().joinpath(SEED_FILE).read_bytes())
    delay = now - seed.anchor
    # Whole days between the two UTC dates, not the whole days in `delay`: those are
    # one fewer whenever `now` is earlier in its day than the anchor is in its own,
    # which would show a repair "scheduled for tomorrow" as due today.
    days = utc_day(now) - utc_day(seed.anchor)
    for aircraft in seed.aircraft:
        store.add_aircraft(aircraft)
    for log in seed.write_ups:
        write_up_id = store.file(log.tail, _moved(log.reported, delay, days))
        for event in log.later:
            store.append(write_up_id, _moved(event, delay, days))


def _moved[E: Event](event: E, delay: timedelta, days: timedelta) -> E:
    """Move an event's time by `delay`, and a repair date by `days`."""
    update: dict[str, object] = {"at": event.at + delay}
    if isinstance(event, Scheduled):
        update["on"] = event.on + days
    return event.model_copy(update=update)
