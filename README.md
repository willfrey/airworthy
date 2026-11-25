# airworthy

Track aircraft write-ups from report to repair, and which aircraft can fly.

## Run it

Requires [uv](https://docs.astral.sh/uv/), which fetches Python and everything else.

```
uv run airworthy                 # then open http://127.0.0.1:8000
uv run airworthy --port 9000     # on another port
uv run airworthy --db fleet.db   # keep the data in a file between runs
```

Each start without `--db` gets a fresh copy of the sample fleet: six aircraft whose
write-ups are dated relative to the moment of the start. With `--db`, the sample fleet
is loaded only while the file holds no aircraft.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```
scripts/check       # every check CI runs
scripts/mutation    # mutation testing
```

`AGENTS.md` has the conventions and the gates.
