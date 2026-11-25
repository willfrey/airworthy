# Build plan: aircraft write-ups, report to repair

Two hours, executed top to bottom. Every toolchain question below was settled in a
scratch probe before the clock (2026-11-19); nothing here needs re-checking.
The store, form and mutation patterns were probed again on 2026-11-24, on the v0.6.3
skeleton with pydantic-ai 2.73; what that found is written in below.
This plan is committed at `docs/build-plan.md` with the first PR, as it stood when the
clock started, and DECISIONS.md says what the preparation covered: the stack choice, the
gate probes, this plan, and a timing rehearsal that was stopped and discarded.

## T+0 (5 min): confirm the product calls

Each has a default; confirm or flip it, then paste the list into DECISIONS.md as
"questions I'd have asked the PM".

| # | Question | Default |
|---|---|---|
| 1 | Does "at any moment" mean now, or any past time too? | Any time: an append-only event log per write-up, folded to a state at time t. |
| 2 | Must a write-up be scheduled when filed? | No. Unscheduled is a state, shown in a "needs scheduling" queue. |
| 3 | Can a write-up be resolved without being scheduled first? | Yes (fixed on the spot); scheduling exists so nothing is forgotten. |
| 4 | Can severity change after filing? | Yes, as an event. Raising to high grounds at once; lowering releases. |
| 5 | Can a resolved write-up be reopened? | Yes, as an event. A reopened high re-grounds. |
| 6 | Who signs off a repair? | The resolver's name. No second inspector (real airlines require one for some work: say so). |
| 7 | Auth and roles? | None. The forms offer the seeded people's names; any non-blank name is accepted. |
| 8 | Overdue repairs? | Flag a scheduled date in the past. No MEL deferral limits (out of scope, say so). |
| 9 | Do medium and low ever ground? | Never. |
| 10 | AI severity? | Suggests only; a human picks; picking lower than the suggestion warns and records both. Off without an API key. |
| 11 | Which clock decides "overdue" and reads a past time? | Event times are UTC instants from the server clock. "Overdue" compares the scheduled date with today in UTC, a named constant rather than a setting (DECISIONS.md: a real airline would use its base's zone). An `?at=` time without a zone is read as UTC, and the page says so. |
| 12 | Two people act on one write-up at once? | The second action is checked against the first one's result; resolving twice is refused, not recorded twice. |
| 13 | Can a resolved write-up be scheduled, or resolved again? | No. Both are refused until it is reopened, which also settles a schedule that races a resolve. |
| 14 | Can severity be corrected on a resolved write-up? | Yes. It grounds nothing while resolved; a reopen then grounds, or not, at the corrected severity. |
| 15 | Does a reopened write-up keep its repair date? | No. It reopens unscheduled, back in the "needs scheduling" queue. |
| 16 | Can an open write-up be rescheduled, or scheduled for a past date? | Yes to both. A new date replaces the old; a past date shows as overdue at once. |
| 17 | Under `?at=`, overdue against which day? | The viewed moment's UTC date, so a past view shows what was overdue then. |
| 18 | Can the question box change anything, or be the record? | No to both. Its tools only read, and its answer is marked as generated, with the board as the record. Off without an API key. |

## Stack (probed: installs on 3.15 and passes every gate)

Runtime: `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `pydantic` (already),
`pydantic-ai-slim[anthropic]` (stretch only). Dev: `httpx2`. Storage: stdlib `sqlite3`.

Gate patterns, all verified:

- Routes via `app.add_api_route(path, fn, methods=[...])`, never `@app.get`: the
  decorators break mypy's `disallow_any_decorated` / `disallow_any_expr` in the package.
- Render with `jinja2.Environment(loader=jinja2.PackageLoader("airworthy"),
  autoescape=True)` and return `HTMLResponse(...)`; `TemplateResponse`'s
  `dict[str, Any]` context trips `disallow_any_expr`.
- Tests use `fastapi.testclient.TestClient` with `httpx2` installed (plain `httpx`
  warns, and pytest's filterwarnings makes that an error; pyrefly also loses types).
- `[tool.deptry.per_rule_ignores] DEP002 = ["python-multipart"]`, with a comment:
  FastAPI imports it, no module of ours does.
- Add each module to the import-linter `layers` list (it is exhaustive).
- pydantic-ai: `Agent("anthropic:claude-opus-5-5", output_type=Suggestion,
  instructions=..., defer_model_check=True)` builds with no key; tests run
  `with triage.agent.override(model=TestModel(custom_output_args={...})):`.
- Serve with a `--port` option (default 8000).
- `sqlite3.connect(..., autocommit=True)` (Python 3.12+), so explicit `BEGIN IMMEDIATE`
  controls the transaction rather than the module's implicit ones.
- From AGENTS.md: domain models subclass the base model in `model.py`, so add it to
  Ruff's `runtime-evaluated-base-classes`; cast a library's `Any` once, in its wrapper;
  build lookup tables as literals (mutmut can't reach a table built at import).

Probed 2026-11-24, each by a run:

- Handlers are plain `def`, never `async def`: pyrefly rejects an async handler passed
  to `add_api_route` (`partially-unknown-type`).
- A form arrives as one parameter, `form: Annotated[ActionForm, Form()]`, whose fields
  are all optional text. The handler builds `fields = {**form.posted(), "at": clock()}`
  in a variable (mypy rejects the dict written inside the call) and validates it into
  the event type, so a bad date is a `ValidationError` the handler turns into the 400.
  A required field on the form model has FastAPI answer 422 JSON before the handler
  runs. `posted()` is the base model's typed `model_dump(exclude_unset=True)`.
- A `sqlite3` connection can't leave the thread that opened it, and FastAPI runs each
  handler on a worker thread, so the store opens a connection per operation (§ store).
  Close every connection with `contextlib.closing`, in tests too: Python warns about an
  unclosed one, and `filterwarnings = ["error"]` fails the session after its tests pass.
- `PRAGMA foreign_keys = ON` on every connection: SQLite ignores `REFERENCES` without it.
- Text that its reader takes case-insensitively gives mutmut equivalent mutants inside a
  function: SQL statements, `"seed.json"` and template names (on macOS's filesystem;
  CI's would catch those), and `methods=["POST"]`. Name each as a module-level `Final`
  constant, where the probe's survivors went away, and leave `methods` off a GET route.
- Pydantic 2.14 refuses every value of a `tuple[X, *tuple[X, ...]]` field, so a type
  that holds one is a stdlib frozen dataclass.
- The skeleton has no entry point: `[project.scripts] airworthy = "airworthy.web:main"`
  goes in with the web PR, or the README's `uv run airworthy` finds nothing.

Probed 2026-11-24 for the fleet-questions agent (§ `ops.py`), each by a run that ended
with `scripts/check` green and one mutation survivor, the `methods=["POST"]` above:

- A tool is a plain function, `def fleet_status(ctx: RunContext[Reads], at: datetime |
  None = None) -> ...`, with no decorator. The tools go in a module-level `Final` tuple
  passed as `Agent(..., deps_type=Reads, tools=TOOLS)`: mypy rejects the list written
  inside the call (its type contains `Any`). A tool may return a Pydantic model, a
  stdlib frozen dataclass, a union or tuple of them, or a `datetime`.
- pydantic-ai reads a tool's annotations at run time, and Ruff wants an import used
  only in annotations moved out. `lazy from pydantic_ai import RunContext` (and `lazy
  from datetime import datetime`) satisfies both. Ruff's own unsafe fix, a
  `TYPE_CHECKING` block, is a `NameError` when the agent is built.
- `agent.run_sync` leaves an event loop open on the thread that called it. On a
  handler's worker thread Python warns about it, and the session fails after its tests
  pass. The function that runs the agent owns the loop: `with
  closing(asyncio.new_event_loop()) as loop:`, then `asyncio.set_event_loop(loop)` and
  `agent.run_sync(...)`. `asyncio.run(agent.run(...))` fails pyrefly
  (`partially-unknown-type`), for the reason an `async def` handler does.
- Tests script the model with `FunctionModel`: its function calls each tool with
  chosen arguments, then answers with the question and what the tools returned, and
  the test asserts that text. `TestModel` alone left three survivors, since it sends no
  arguments and ignores the question. Inside a handler,
  `agent.override(model=TestModel(custom_output_text=...))` works through `TestClient`.

Model access: pydantic-ai's Anthropic provider reads `ANTHROPIC_API_KEY` from the
environment. The key lives in the gitignored `.env` at the checkout root; Claude Code's deny rule
hides `.env` from the agent's sandbox, so I start real runs myself with
`! uv run --env-file .env ...` and the agent never sees the key. Real runs (the demo
and the labeled set) use my own key. Never print the key; tests never need
it. The README tells a reader to export their own key or skip the feature.

Verified with two real calls on 2026-11-19 (scratch probe): pydantic-ai's default
output mode works with Claude Opus 5.5, no 400 (it relaxes `tool_choice` to `auto`).
"Cracked windshield" came back high and "reading light inoperative" came back low.
Measured usage: 348 in / 429 out and 340 in / 121 out tokens, about $0.014 for both at
$4 / $20 per million, so the 15-item labeled set costs about $0.15 (an estimate
extrapolated from those two calls). Lessons:
- Keep the reason's substance: the windshield answer named what would change the call
  (a crack within the manual's damage limits may be deferrable), which is what the
  person picking the final severity needs. Instruct "a short reason that names
  anything that would change the severity", not "one sentence"; in the form, show
  the severity and first sentence with the rest behind a "why" toggle.
- `result.usage` is a property in pydantic-ai 2.71; calling it warns, and pytest's
  filterwarnings would turn that into an error.
- pydantic-ai prints a Logfire banner on first model use; set
  `PYDANTIC_AI_NO_BANNER=1` for a clean server log in the demo.
- The windshield reason mentioned MEL deferral limits on its own: a ready-made line
  for DECISIONS.md about why MEL is out of scope.

## Concepts

- **Write-up**: a reported defect on one aircraft, carried from report to repair.
  Operational principle: someone reports a defect with a severity; it is scheduled for
  repair; a mechanic resolves it; if the defect comes back, it is reopened. Its
  severity can be corrected at any point.
- **Airworthiness**: whether an aircraft is cleared to fly at a given moment. An
  aircraft is grounded exactly while it has an open high-severity write-up, and the
  answer names those write-ups. Derived from write-ups, never stored.
- **Severity triage** (stretch): a suggested severity for a description, for a human
  to accept or override. It informs the report and never decides it.
- **Fleet questions** (stretch): a question in plain words about the fleet, answered
  from the same reads the pages use. Operational principle: someone asks "which
  aircraft can't fly right now, and why?"; the agent calls read-only tools and answers
  in a sentence or two naming tails and write-ups. It records nothing and decides
  nothing.

Design it twice, settled: the alternative to an event log is a current-state table
plus a history table, two copies of the truth (the board reads one, the past-time
view the other). The event log is the one source; DECISIONS.md says so.

## Components

Layers, top to bottom: `web` → `triage` / `store` → `fleet` → `writeup` → `(model)`.

**`writeup.py`: the write-up concept, pure, no I/O. Most of the tests live here.**
- `Severity(StrEnum)`: high, medium, low; it crosses the DB, form and LLM
  boundaries. It is the one home for each severity's decisions: `grounds` (an
  exhaustive `match`; only high), `label`, and `description` (the triage prompt reads
  it). It also holds an explicit rank, which `downgraded(reported)` compares by when
  the pick is lower than the suggestion: a `StrEnum`'s own `<` is alphabetical, and
  that puts medium above high. Nothing else branches on a severity.
- Events: frozen models with a `kind: Literal[...]` field, each with `at` (an aware UTC
  datetime) and `by`. `Reported(severity, description, suggested: Suggestion | None)`
  opens a write-up and is not a follow-up. The follow-ups are a discriminated union:
  `FollowUp = Reclassified(severity) | Scheduled(on: date) | Resolved(note) |
  Reopened(reason)`. `severity` on `Reported` is required and human-chosen;
  `suggested` only records the model's view, so no model output can set the severity
  that grounds an aircraft. `by`, `description`, `note` and `reason` share one `Text`
  type, stripped and at least one character long, so a sign-off can't be blank.
- `WriteUp(id, tail, reported: Reported, later: tuple[FollowUp, ...])`: what the store
  hands back and `fleet` reads. A write-up with no report, or with two, can't be built,
  so neither needs a rule in `apply`.
- State: `Open(severity, scheduled_for: date | None) | Closed(severity, at, by, note)`,
  a sum type, so no state is both. `Closed` is the resolved state; the event already has
  the name `Resolved`. Both carry `as_of`, the time of the last event applied, which is
  what the rule about an earlier `at` reads.
- `opened(reported) -> Open`, and `apply(state: State, event: FollowUp) -> State`: the
  one transition rule, by the table below. It raises a domain error for a refused cell
  and for an `at` earlier than the state's `as_of`. Its `match` over `FollowUp` ends in
  `assert_never`.

  | Follow-up | on `Open` | on `Closed` |
  |---|---|---|
  | `Reclassified` | the new severity | the new severity, still closed (call 14) |
  | `Scheduled` | the new date, replacing any earlier one (call 16) | refused (call 13) |
  | `Resolved` | `Closed` | refused (calls 12 and 13) |
  | `Reopened` | refused | `Open` with no date (call 15) |

- `state_at(write_up, t) -> State | None`: `None` before the report's `at`; otherwise
  `opened`, then `apply` folded over the follow-ups with `at <= t`, in log order. Replay
  and validation are the same function, so a stored log that `apply` refuses fails
  loudly on read.
- `needs_scheduling(state)` and `overdue(state, today)`: an open write-up with no date,
  and one whose date is before `today`. Both are facts about a write-up, so they live
  here and not in `fleet`.

**`fleet.py`: the airworthiness concept, pure.**
- `Aircraft`: tail number, type.
- `status_at(write_ups, t) -> Cleared | Grounded`, where `Grounded.by` is a non-empty
  tuple (`tuple[WriteUp, *tuple[WriteUp, ...]]`) of the open write-ups whose severity
  `grounds`. No boolean, and no grounded-by-nothing state. `Cleared` and `Grounded` are
  stdlib frozen dataclasses: nothing deserializes them, and Pydantic can't validate that
  tuple type (§ Stack).

Laws, each with its enforcement site (the rank is from § Ranked work):
- Grounded at t iff some write-up's state at t is open with a severity that grounds:
  a Hypothesis property (rank 3). The test works its expected answer from the generated
  events themselves (of the report, resolves and reopens at or before t, the last is
  not a resolve; the last severity set is literally high), calling neither `state_at`
  nor `grounds`. An expected answer built from those two changes with them, and the
  break listed below would leave the test green.
- No future leakage: appending events after t never changes `status_at(..., t)`: a
  Hypothesis property (rank 8). This is what makes the past-time view trustworthy.
- Reopen is a deliberate non-monotonic step ("resolved" is not forever): a comment on
  `Reopened`, not a law.
- Event round-trip: dumping an event to JSON and validating it back is the identity: a
  Hypothesis property over generated events, through the store's `TypeAdapter`
  (rank 9; until then, rank 4's example test on hand-built events).

Each test names the break that must turn it red. The build makes that break once,
sees red, and restores it, before calling the rank done. mutmut covers small edits,
and it drops a `case` arm, which `assert_never` then turns into a type error. It never
deletes any other statement or reorders two (probed 2026-11-24), so these are run by
hand:

| Test | Break that must turn it red |
|---|---|
| Hand-worked awkward paths | Each path's rule removed from `apply`, one at a time |
| Grounded property | `grounds` true for medium too |
| No future leakage | `state_at` without the `at <= t` filter |
| Round-trip | `suggested` left out of the dump |
| Double-resolve rule | `apply` accepting `Resolved` on a closed write-up |
| Lock test | `BEGIN IMMEDIATE` deleted; the read moved before it (both checked 2026-11-20) |
| Seed test | One story's event changed (a resolve deleted) |

Generating valid event sequences: draw a report and random follow-ups, and fold them
through `apply`, skipping the ones it refuses. No hand-written generator of valid
sequences.

Hand-worked tests: one for each cell of the transition table, and one for each awkward
path: raise to high, lower from high, reopen a high, resolve before scheduling, correct
the severity of a closed write-up and then reopen it, an event at exactly t, an event
after t (not applied; the property that covers this is rank 8, below the cut line), and
two events at the same instant (ordered by log sequence).

**`store.py`: sqlite3 adapter.**
- Tables: `aircraft(tail PK, type)`, `write_ups(id INTEGER PRIMARY KEY, tail REFERENCES
  aircraft)` and `events(seq INTEGER PRIMARY KEY, write_up_id REFERENCES write_ups,
  body TEXT)`. `body` is the whole event as JSON through a `TypeAdapter` over
  `Reported | FollowUp`; no separate kind or time column to fall out of step, and the
  tail is held once per write-up, not on each of its events. Log order is `seq`.
- `Store(connect)` takes a function that opens a connection, and each operation opens
  one and closes it. Handlers run on worker threads, where a connection opened elsewhere
  fails. With a connection each, SQLite is what makes the second writer wait. Probed
  2026-11-24: two racing resolves on one shared connection end with the second raising
  "cannot start a transaction within a transaction"; on a connection each, one is
  recorded and the other refused, which is call 12.
- `file(tail, reported) -> id`: inserts the write-up and its report in one transaction,
  and the database mints the id. The foreign key refuses an unknown tail.
- `append(write_up_id, follow_up)`: inside one `BEGIN IMMEDIATE` transaction, load the
  write-up, fold it, `apply` the new follow-up, and insert it. SQLite serializes
  the writers, so two concurrent resolves can't both pass the check. Open each
  connection with `sqlite3.connect(path, autocommit=True)`, so the module opens no
  transaction of its own and our `BEGIN IMMEDIATE` is the one that runs. End it with
  `execute("COMMIT")`, or `execute("ROLLBACK")` when `apply` refuses: under
  `autocommit=True`, `connection.commit()` and `with connection:` do nothing, and an
  insert finished that way is gone when the connection closes (probed 2026-11-24). So
  every write test reads its write back through a second call. Two more tests:
    - **The rule:** resolve, then resolve again through `append`; the second is
      refused. This is `apply`'s rule and would pass without the transaction.
    - **The lock:** a second connection runs `BEGIN IMMEDIATE` and holds it. The
      store's `connect`, for this test, opens with `timeout=0` and records each
      connection's statements with `set_trace_callback`; `append` must raise
      `sqlite3.OperationalError` ("database is locked") having run no `SELECT`. That
      is the promise: nothing is read for the check until the write lock is held. No
      threads or sleeps.
  Verified 2026-11-20 in the scratch copy, with the store then holding one connection,
  against three versions of `append`: the right one passes; with no transaction, and
  with the read before `BEGIN IMMEDIATE`, it fails. An earlier draft asserted only
  "database is locked", which both broken versions also raise (the held lock blocks any
  write), so it tested nothing. Run again 2026-11-24 through `connect`, against the
  same three versions, with the same result.
- The event's `at` comes from the server clock, passed in by the caller (tests pass
  fixed times).
- `write_ups(tail)`, `all_aircraft()`: reads that hand back events for `writeup` to fold.
- `seed(store, now)`: loads the sample data described in § Sample data.

## Sample data

The seed is data, not code: `src/airworthy/seed.json`, read with
`importlib.resources` and validated through the store's `TypeAdapter`, so a malformed
seed fails on load. mutmut is not the reason: it leaves module-level literals alone, so
a Python module of them would cost no mutants either.

- **One format.** The file holds aircraft, and each write-up as its report and
  follow-ups in the store's own event format, through the same `TypeAdapter`, timed as
  if now were a fixed anchor (`2026-01-15T12:00Z`, a field of the file). Loading shifts
  every `at` by `now - anchor`, and every `Scheduled.on` by the days between the two
  UTC dates, `now.date() - anchor.date()`. The whole days in `now - anchor` are one
  fewer whenever the app starts before 12:00 UTC, which would show "scheduled for
  tomorrow" as today. So the overdue flags and the past-time view are right whenever it
  runs, and there is no second "days ago" schema.
- **Loaded through `file` and `append`.** Each follow-up goes through `apply`, so a seed
  that breaks a rule fails on load, the same as a user action.
- **Fresh by default.** `main()` builds a new seeded DB on each start, so the README's
  walk-through always matches what a reviewer sees. `--db PATH` keeps a DB, seeding it
  only when it is created.
- **People.** Four invented names for `by`: two mechanics, a pilot, and a maintenance
  controller. Tails are invented `N1xxAW` registrations; the types are real.

One story per aircraft, so the first page load shows every state:

| Tail | Type | Story | Now | Two days ago |
|---|---|---|---|---|
| N101AW | A320 | A low (inoperative reading light) resolved last week | cleared | cleared |
| N102AW | A320 | A high (cracked windshield outer pane) reported 3 h ago, scheduled for tomorrow | grounded | cleared |
| N103AW | 737-800 | A high reported last week and resolved yesterday; a medium still open, its repair date two days ago | cleared, overdue flag | grounded |
| N104AW | E175 | Two highs open, one scheduled and one not | grounded by two; in "needs scheduling" | grounded |
| N105AW | E175 | A medium raised to high yesterday. Its report recorded a high suggestion and a human pick of medium, so the downgrade warning shows | grounded | cleared |
| N106AW | ATR 72 | A high resolved, then reopened today; a low fixed on the spot without scheduling; a high lowered to medium | grounded (reopened); in "needs scheduling", since a reopen clears the date | cleared |

Some seeded reports carry a `suggested` value, so the AI record shows in the demo with
no API key. The seed's descriptions are separate from the labeled set (rank 10): one
demonstrates the app, the other measures the model.

Seed test, through `seed` and `status_at` with a fixed `now`: each tail's status in
both columns above. The fixed `now` is before 12:00 UTC, and the test also checks the
overdue flag and the "needs scheduling" entries of the Now column, and N105AW's
downgrade warning, none of which `status_at` carries. That pins the stories, and with
them the README's walk-through.

**`web.py`: FastAPI and Jinja2, built by `create_app(store, suggester, clock)`, and
from rank 7 `create_app(store, suggester, ask, clock)`.**
- No module-level state: the store, the suggester (`Suggester | None`; `None` without
  an API key, which hides the suggestion box), the question answerer (`ops.Ask |
  None`, hidden the same way) and the clock are passed in, so tests pass fakes and
  patch nothing.
- `GET /`: the fleet board, one row per aircraft (cleared, or grounded and by which
  write-ups), a "needs scheduling" count that links to the work list, overdue flags, and
  an `?at=` time picker for past times. Each row also counts the aircraft's open
  write-ups, so a cleared aircraft with open mediums doesn't look like one with nothing
  wrong.
- `GET /work`: the work list, every open write-up across the fleet as of now, each
  linking to its aircraft. This is the "needs scheduling" queue of call 2: unscheduled
  first, then by repair date, so the overdue ones lead the scheduled; within either
  group, the higher severity first. The order is one pure function in `writeup.py`,
  `worklist(write_ups, today)`, built and tested with this page; the page only renders
  it. If the stage runs long this page is the first thing dropped, and the board keeps
  its count without the link.
- `GET /aircraft/{tail}`: write-ups with their event history and the action forms.
- `POST /aircraft/{tail}/write-ups`: file a write-up (it creates the write-up).
- `POST /aircraft/{tail}/suggestion` (rank 6): where the "Suggest" button posts. It
  takes the description, asks the suggester, and re-renders the aircraft page with the
  description kept in the new write-up form and the suggestion shown. It files nothing,
  and it is registered only when there is a suggester.
- `POST /questions` (rank 7): where the board's question box posts. It builds
  `ops.Reads` from the store and the clock, calls `ask(question, reads)`, and
  re-renders the board with the question kept and the answer under it, marked as
  generated (call 18). It records nothing, and it is registered only when there is an
  `ask`. A blank question is the same 400 as any other bad form.
- `POST /write-ups/{id}/events`: every other action. The form is parsed into
  `FollowUp` at this boundary; adding a follow-up kind means a union member, an arm in
  `apply`'s `match`, and a form partial, and the type checker finds the `match`.
- A domain error re-renders the page with the message and a 400, and so does a form
  that doesn't validate (a bad date, a blank name). An unknown tail or write-up id is a
  404. Success redirects 303.
- `main(argv, serve=uvicorn.run)`: uvicorn on `--port`; a fresh seeded DB each start
  unless `--db PATH` is given. The fresh DB is a file in a new temporary directory,
  since every connection to `:memory:` gets its own empty database. The server is a
  parameter because coverage has no exclusion for `main` and nothing may be patched: its
  test passes a `serve` that records the call. Probed 2026-11-24, down to the installed
  `airworthy` command serving a page:
    - `serve` is typed by a `Protocol`, `__call__(self, app: FastAPI, *, port: int) ->
      None`, which `uvicorn.run` satisfies.
    - The options are read into a typed `argparse.Namespace` subclass, passed as
      `parse_args(argv, namespace=Options())`. pyrefly rejects reading a plain
      namespace's attributes, cast or not.
    - `ArgumentParser` gets no `prog` and no help text, and the DB's file name is a
      module-level constant: each is text no test notices, so a surviving mutant.

**`triage.py` (stretch): the severity triage concept.**
- `Suggestion(severity, reason)` lives in `writeup.py`, since `Reported` stores it;
  `triage` imports it from there, keeping the layers pointing down.
- `Suggester` protocol: `suggest(description) -> Suggestion`; the pydantic-ai
  implementation wraps the module-level `agent` (the form § Stack verified), whose
  instructions ask for a short reason naming anything that would change the severity.
  At module level the instructions are text mutmut leaves alone, like the SQL.
- Flow: the new write-up form has a "Suggest" button that posts the description to
  `POST /aircraft/{tail}/suggestion` (§ web), which
  re-renders the form with the suggestion and its reason shown beside the severity
  field (first sentence, the rest behind "why"). The field itself stays unselected and
  required, so submitting is always a pick and never an acceptance by default. The
  suggestion rides back in hidden fields and is stored on `Reported.suggested`; with no
  auth, that record is as trustworthy as `by` is, and DECISIONS.md says so. The slow
  model call never sits inside the filing request.
- A 15-item labeled set and a script reporting agreement, with the score in the README.
- `suggest` runs its agent inside a loop it opens and closes (§ Stack, the `run_sync`
  note), so a test may run it inside a handler.

**`ops.py` (stretch): the fleet questions concept, an agent with read-only tools.**
- `Reads`: a frozen dataclass of the calls the tools may make, each a plain callable:
  `fleet(at | None)` (every aircraft's `Cleared | Grounded`), `write_ups(tail)` (that
  aircraft's write-ups with their current state, or `None` for an unknown tail),
  `work()` (the work list, only if rank 5 built it) and `now()`. `web` builds it from
  the store and the clock. `ops` imports `fleet` and `writeup` for the types and never
  the store, so no tool can reach a write: the type has no call that changes anything.
- One tool per read, each a one-line function that passes its arguments to the read
  (§ Stack for the form). `current_time` is a tool because the model needs today's
  date before it can turn "yesterday morning" into an `at`.
- `agent`: module-level, the same model as triage, `defer_model_check=True`, no
  `output_type` (the answer is text). Its instructions, module-level text: answer only
  from the tools; name tails and write-up ids; say so when the tools don't hold the
  answer; two or three sentences.
- `ask(question, reads) -> str` is the module's one function, and `Ask` is its type.
  `main` passes `ops.ask` when the key is set and `None` otherwise.
- Tests. `ops`: the scripted model calls every tool with chosen arguments, and the
  test asserts the answer text and what each fake read was called with. Break: a tool
  that drops its argument (`fleet(None)`), and `ask` without the question. `web`: a
  fake `ask` that returns what the reads gave it, against the seeded store, so the
  test fails if `Reads` is wired to anything but the store; and no route without one.
- Not probed: a failed model call (a bad key, no network). The handler should show
  "no answer" with a 502 rather than a traceback; find which pydantic-ai error to
  catch by raising inside the scripted model, and catch it in `ask`.
- For DECISIONS.md: write-up descriptions are text anyone can file, and the model
  reads them, so a description can mislead an answer. It cannot change data, which is
  why the tools are read-only and the answer is marked as generated.

## Execution order

The repository is `willfrey/airworthy`. `main` starts at two commits: the
skeleton generated from copier-python v0.6.2, and its update to v0.6.3, which took
GitHub's #1. Every stage below lands as its own squash-merged PR, so `main`'s history
is the list of PR titles. The PR column counts this plan's stages, so GitHub's number
for each is one higher (stage 1 is #2).

| Clock | PR | Branch | Title | Done when |
|---|---|---|---|---|
| 0–5 | 1 | `docs/product-decisions` | `docs: record the product questions and their answers` | DECISIONS.md § 1 holds the confirmed calls; this plan is committed unchanged |
| 5–35 | 2 | `feat/write-up-events` | `feat: fold a write-up's events into its state` | rank 1; check and mutation green |
| 35–52 | 3 | `feat/airworthiness` | `feat: derive an aircraft's airworthiness from its write-ups` | ranks 2–3; check and mutation green |
| 52–72 | 4 | `feat/event-store` | `feat: store events in SQLite and seed the sample fleet` | rank 4; round-trip, double-resolve, lock and seed tests green |
| 72–93 | 5 | `feat/fleet-board` | `feat: serve the fleet board and the write-up actions` | rank 5; TestClient tests green, every action clicked through |
| **93** | | | **Cut line:** stop wherever PRs 2–5 stand and go to PR 10 | |
| 93–105 | 6 | `feat/severity-triage` | `feat: suggest a severity for a new write-up` | rank 6; gates green without a key |
| | 7 | `feat/fleet-questions` | `feat: answer questions about the fleet from read-only tools` | rank 7; gates green without a key, one real question asked |
| | 8 | `test/history-properties` | `test: check past-time reads and event round-trips over generated histories` | ranks 8–9 |
| | 9 | `test/triage-agreement` | `test: measure the severity suggestions against a labeled set` | rank 10; score in the README |
| 105–120 | 10 | `docs/readme-and-decisions` | `docs: say how to run it, what was built and what was left out` | README, DECISIONS.md §§ 2–5; CI green |

The 105–120 slot is protected: the README and DECISIONS.md are how a reader runs the
app and sees what was decided and left out, so no rank takes time from it. The 93–105 slot is twelve minutes for four PRs, and
no stage's time has been measured, so PR 7 is built only if PRs 2–6 finish early. The
two hours are a strong suggestion: a few minutes over to finish a stage already green
locally is fine, and starting a new stage past 105 is not.

### How each PR runs

- **A PR adds what it uses.** There is no scaffolding PR: each PR adds its own module,
  its line in the import-linter `layers` list, and its dependencies with `uv add`.
  deptry fails on a dependency nothing imports, so `fastapi`, `uvicorn`, `jinja2`,
  `python-multipart` (with its `DEP002` ignore) and dev `httpx2` arrive in PR 5, and
  `pydantic-ai-slim[anthropic]` in PR 6. PRs 2–4 need nothing new: `pydantic` and
  `hypothesis` are in the skeleton, and `sqlite3` is in the standard library.
- **Before pushing:** `scripts/check` and `scripts/mutation` green, and the stage's
  breaks from § Components made and seen red.
- **Open as a draft**, with a Conventional Commits title (`pr-title-lint.yaml` checks
  it; the squash merge uses it as the commit message). CI and the mutation workflow
  skip a draft, so they run when I mark it ready. I merge; the agent never does.
- **Every PR targets `main` and holds one stage; nothing is force-pushed.** Work on the
  next stage starts locally at once, on a branch cut from the previous stage's tip,
  and stays unpushed. Once the earlier PR is squash-merged, that local branch moves
  onto the new `main` with `git rebase --onto origin/main <previous tip>`, and only
  then is it pushed and its PR opened. So each PR's diff is its own stage against
  `main`, and CI runs on exactly that.
- **Cut PRs are not opened.** Whatever PRs 6–9 are dropped go in DECISIONS.md § 3 as
  "left out, would add next".

### Ranked work

Ranks 1–5 are the app; the cut line falls after them. Ranks 6–10 are extras in the
order they get built, so an overrun drops them from the bottom up. Whatever is
dropped goes in DECISIONS.md as "left out, would add next".

1. `opened`, `apply`, `state_at`, `needs_scheduling`, `overdue`, and the hand-worked
   tests for every table cell and awkward path. The awkward cases are where a tracker
   like this goes wrong, and everything else folds through `apply`.
2. `status_at` (grounded and by which write-ups).
3. The event-sequence generator and the "grounded at t iff an open high" property:
   the rule the brief states, checked over generated histories. If the domain slot
   runs past 52, cut this rank and keep the hand-worked tests.
4. The store: `file`, `append` inside `BEGIN IMMEDIATE`, the one-JSON-body schema, the
   round-trip test on a few hand-built events, the double-resolve rule test and the
   lock test (about 5 minutes), and `seed.json` with its test (§ Sample data). The seed is about 5 minutes of the
   store slot, and the README's walk-through and the demo depend on it.
5. The web: the board with `?at=` and each row's open count, the aircraft page, the
   filing route, the single events route, and a domain error shown with a 400; then the
   work list, dropped first if the stage runs long.
6. Triage: `Suggester`, the "Suggest" route and step, and `Reported.suggested`. It is
   one model call, with no tools.
7. Fleet questions: `ops.ask` with its read-only tools, and the board's question box.
   It is the one tool-using agent in the build, so it ranks above the two properties
   below, which re-check rules the hand-worked tests already pin. The demo asks it one
   question about now and one about a past time.
8. The no-future-leakage property (the generator from rank 3 is already there).
9. The event round-trip property, generated, in place of rank 4's hand-built events.
10. The 15-item labeled set and its agreement script.

Already left out: a configurable base time zone (UTC is a named
constant) and a threaded concurrency test (the lock test checks the transaction
without timing).

After the clock: record the demo video and export the session log.

Run `scripts/mutation` at each "done when", not only at the end: it fails on any
surviving mutant, and a late survivor in the web layer is the likeliest overrun.

## DECISIONS.md skeleton

1. Questions for the PM, and my answers (the table above, as settled).
2. What I built.
3. What I left out, and why: auth and roles, second-inspector sign-off, MEL
   deferral limits, notifications, editing or deleting a write-up (the log is
   append-only; a correction is a new event), adding aircraft from the UI (seeded),
   Postgres. Also: who will do a repair (scheduling records a date and who set it, with
   no assignee), duplicate reports of one defect (two write-ups, each resolved on its
   own), and a JSON API (the pages are the only interface).
4. Next, with more time: a grounding history per aircraft ("grounded from Tuesday 09:00
   to Wednesday 14:00"), first because the event log already holds it; then the
   fleet-questions agent if rank 7 was cut, and for it a labeled set of questions with
   known answers, since nothing measures its answers; MEL categories, inspector
   sign-off, audit export.
5. AI use: how the session went, with the log attached.
