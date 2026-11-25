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

## A walk through the sample fleet

The board at `/` is the answer to "which aircraft can fly right now". On a fresh start
it shows two of six aircraft cleared, and one story per aircraft:

| Aircraft | What the board shows | Why |
|---|---|---|
| N101AW | cleared | its one write-up, a low, was resolved last week |
| N102AW | grounded | a high reported three hours ago, repair set for tomorrow |
| N103AW | cleared, one overdue | its high was resolved yesterday; a medium is past its repair date |
| N104AW | grounded by two | two highs open, one with no repair date |
| N105AW | grounded | a medium raised to high yesterday; its report was filed below what a model suggested, and the history says so |
| N106AW | grounded | a high resolved and then reopened today, so it has no repair date again |

Things to try:

1. **Ground and release.** Open N104AW and resolve one of its two highs: the aircraft
   stays grounded by the other. Resolve that one too and it is cleared.
2. **Every issue gets a date.** The board's "Needs a repair date" column lists the open
   write-ups nobody has scheduled. Set a date in the past and the write-up moves to
   "Overdue".
3. **A past moment.** Enter a time two days back in "Show the fleet as it stood at
   (UTC)". N103AW and N104AW are grounded, the other four are cleared, and the pages
   offer no actions: a past view can't be changed. The same view is a link: `/?at=`
   followed by a time such as `2026-11-23T12:00`.
4. **Corrections are events.** On N106AW, one write-up was reported high and lowered to
   medium with a reason, which is the one way an aircraft is released without a
   repair. Change a severity yourself: the form refuses without a reason.
5. **An action the state doesn't allow.** A page offers only the actions a write-up's
   state allows. Open one write-up in two tabs, resolve it in the first, then resolve
   it in the second: the second is refused and nothing is recorded twice.

Any non-blank name is accepted in "Your name": there is no sign-in, which
`DECISIONS.md` discusses with everything else that was left out.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```
scripts/check       # every check CI runs
scripts/mutation    # mutation testing
```

`AGENTS.md` has the conventions and the gates.
