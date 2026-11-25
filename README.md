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

### Severity suggestions (optional)

With an Anthropic API key in the environment, the form that files a write-up gains a
"Suggest a severity" button. It asks Claude (`claude-opus-5-5`) for a severity and a
reason from the description, and shows both beside the choice. It never fills the
choice in: the person picks the severity, the suggestion is recorded next to it, and a
report filed below its suggestion is marked in the write-up's history.

```
uv run --env-file .env airworthy   # .env holds ANTHROPIC_API_KEY=...
```

Without a key the button is absent and everything else works the same. The sample
fleet's N105AW carries a recorded suggestion, so the marking is visible either way.
Each suggestion is one model call of a few hundred tokens.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```
scripts/check       # every check CI runs
scripts/mutation    # mutation testing
```

`AGENTS.md` has the conventions and the gates.
