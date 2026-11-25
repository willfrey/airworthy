# Decisions

Section 1 was settled before any application code was written. Sections 2–5 were
written at the end of the build.

## 1. Questions I would have asked the product manager, and my answers

The brief's two rules are taken as written: a high-severity write-up grounds its
aircraft until it is fixed, and every write-up needs a repair date. Everything below is
a place where the brief doesn't say, and the call I made.

| # | Question | My answer |
|---|---|---|
| 1 | Does "shows at any moment" mean now, or any past time too? | Now, first: the board is always current. Past times too: each write-up is an append-only log of events, folded to its state at a time t, so the board can be read as of any earlier moment. A past view goes by when an event was recorded, not when the defect appeared: a crack noticed at 09:00 and written up at 11:00 shows the aircraft cleared at 10:00. |
| 2 | Must a write-up be scheduled when it is filed? | No. Unscheduled is a state, listed in a "needs scheduling" queue. I read "every issue needs to be scheduled" as an obligation the app tracks, not a condition of filing: refusing a report because nobody knows the repair slot yet would lose the report. |
| 3 | Can a write-up be resolved without being scheduled first? | Yes. A mechanic who fixes a reading light on the spot shouldn't have to invent a date first. This is the one answer that goes against the brief's literal words. Scheduling exists so nothing open is forgotten, and a resolved write-up has nothing left to forget. |
| 4 | Can severity change after filing? | Yes, as an event that requires a written reason. Raising to high grounds the aircraft at once; lowering from high releases it. Lowering is the one way an aircraft is released without a fix, so the history shows who did it, when and why. |
| 5 | Can a resolved write-up be reopened? | Yes, as an event with a reason. A reopened high grounds the aircraft again. |
| 6 | Who signs off a repair? | The person resolving it, by name. There is no second inspector, which real airlines require for some work. |
| 7 | Authentication and roles? | None. The forms offer the seeded people's names, and any non-blank name is accepted. Every "who" in the history is therefore a claim, not a verified identity. |
| 8 | Overdue repairs? | A repair date in the past is flagged. Deferral limits from a minimum equipment list are out of scope. |
| 9 | Do medium and low ever ground an aircraft? | Never. |
| 10 | Should AI suggest a severity? | Only as a suggestion, if it is built at all (it is a stretch goal): a person always picks the severity, picking lower than the suggestion warns and records both, and the feature is off without an API key. No model output can set the severity that grounds an aircraft. |
| 11 | Which clock decides "overdue" and reads a past time? | Event times are UTC instants from the server clock. "Overdue" compares the repair date with today's date in UTC, a named constant; a real airline would use its base's time zone. A past time given without a zone is read as UTC, and the page says so. |
| 12 | What if two people act on one write-up at once? | The second action is checked against the result of the first. Resolving twice is refused, not recorded twice. |
| 13 | Can a resolved write-up be scheduled, or resolved again? | No. Both are refused until it is reopened, which also settles a schedule that races a resolve. |
| 14 | Can severity be corrected on a resolved write-up? | Yes. It grounds nothing while resolved; a later reopen grounds, or not, at the corrected severity. |
| 15 | Does a reopened write-up keep its repair date? | No. It reopens unscheduled, back in the "needs scheduling" queue. |
| 16 | Can an open write-up be rescheduled, or scheduled for a past date? | Yes to both. A new date replaces the old one, and a past date shows as overdue at once. Refusing a past date would need a "today", and UTC's today is the wrong day for someone scheduling on a US evening. |
| 17 | In a past view, overdue against which day? | The viewed moment's UTC date, so a past view shows what was overdue then. |
| 18 | Could a plain-language question box change anything, or be the record? | No to both, if it is built at all (a stretch goal). Its tools only read, and its answer is marked as generated, with the board as the record. |
| 19 | What happens to a write-up filed in error, such as one against the wrong aircraft? | Not built. The honest tool is a withdrawal event, which I would add next. Until then: lower its severity with a reason, then resolve it with a note saying it was filed in error. |

### Where the build departs from the plan

`docs/build-plan.md` is the plan I prepared before the clock started, committed as it
stood. At the start of the session I had the coding agent review it against the brief,
and I accepted four changes:

- **A severity change requires a reason** (call 4). The plan recorded only who and when.
- **The record of an AI suggestion is added with the suggestion feature**, not in the
  core and the sample data ahead of it. Built the plan's way, cutting the feature would
  leave the demo showing AI suggestions that nothing in the app can produce.
- **The property test that later events never change a past view moves up**, into the
  airworthiness stage, ahead of both AI features. It is what makes call 1's past view
  trustworthy.
- **The README's run instructions land with the web stage**, the first commit at which
  the app can be run, and are finished in the last one.

Call 19 was added in the same review; the plan had no answer for a write-up filed in
error.

## 2. What I built

A server-rendered web app (FastAPI and Jinja2 over SQLite) in seven pull requests, each with its checks and mutation testing green in CI before it merged:

| PR | What it added |
|---|---|
| #3 | `writeup.py`: a write-up is an append-only log of events. One function, `apply`, moves a state by one event, by the table in the module's docstring; nothing stores a state. |
| #4 | `fleet.py`: an aircraft is grounded exactly while it has an open high. Two properties over generated histories check that rule and that a later event never changes a past view. |
| #5 | `store.py`: the events in SQLite, each action checked against the latest state inside one write transaction, so two people resolving at once record one resolution. The sample fleet is data (`seed.json`), loaded through the same rules as a person's actions. |
| #6 | `web.py` and the pages: the board, each aircraft's page with its history and actions, and both as they stood at any past moment. |
| #7 | `triage.py`: an optional severity suggestion from a model, recorded beside the severity the person picked. |
| #9 | A stylesheet for the pages: status as badges, a write-up's history as a timeline, light and dark. No script and no build step. |
| #10 | `ops.py`: a question box on the board, answered by a model through three tools that only read. |

Three choices carry most of the weight:

- **The log is the only source.** "Grounded", "overdue", "needs a repair date" and the
  past view are all computed from events. There is no status column to fall out of
  step with the history, and the past view costs no extra storage.
- **Rules live in one place each.** Which follow-ups a state allows is one table
  (`refusal`); the page offers exactly the actions that table allows, and the store
  refuses by the same table. What a page says about where a write-up stands is one
  `match` that the type checker requires to cover every case.
- **A person's choice grounds an aircraft, never a model's.** The suggestion is shown
  and recorded; no code reads it as the severity.

## 3. What I left out, and why

Out of scope from the start, as section 1 says: sign-in and roles, a second inspector's
sign-off, deferral limits from a minimum equipment list, notifications, adding aircraft
from the pages (the fleet is seeded), editing or deleting (a correction is a new
event), an assignee for a repair, merging duplicate reports, a JSON API, Postgres.

Cut during the build, for time:

- **A labeled set to measure the severity suggestions** (rank 10). So nothing here says
  how often the suggestion agrees with a mechanic. The feature is built and tested
  against stand-in models only.
- **A generated round-trip test for stored events** (rank 9). Hand-built events cover
  each kind.
- **A work list page** of everything open across the fleet. The board's "Needs a repair
  date" and "Overdue" columns carry the same facts per aircraft.
- **A withdrawal event** for a write-up filed in error (call 19).

Known limits in what was built:

- **Names are claims.** The forms take any name typed. Section 1's call 7 said the
  forms would offer the seeded people's names; they don't.
- **A refused form loses what was typed.** A 400 shows the reason and an empty form.
  Asking for a suggestion keeps the description but not the name or severity.
- **Time.** Each action is dated by the server's clock, and a time a form posts is
  ignored. The clock is read before the store's write transaction begins, so of two
  actions on one write-up at nearly the same moment, the one recorded second can
  carry the earlier time and be refused as out of order; the person retries. "Overdue" uses the UTC day.
- **The past view goes by recording time**, as call 1 says.
- **Fresh data on each start** unless `--db` names a file.
- **Suggestions.** The app seals each suggestion to its description with a key made at
  start, so one asked for before a restart is refused after it. Nothing bounds the
  description's length or the model call's time, and each click is a paid call. A
  write-up's description is text anyone can file and the model reads it, so a
  description can try to steer the suggestion; the person still picks.
- **Fleet questions.** This was built last, in the final half hour (see section 5),
  and its answers are not measured: tests script the model, so they show that a
  question and each tool's reads reach it and that its answer reaches the page, not
  that a real answer is right. A write-up's description is text anyone can file and
  the model reads it, so a description can mislead an answer. It can't change data,
  since no tool writes, and the answer is marked as a model's. Nothing bounds a
  question's length or the time an answer takes, and each question is paid model
  calls. A question about the past is answered by recording time, as call 1 says.
- **Rough edges at the form boundary**: a repeated field or an uploaded file is
  refused on the aircraft's page in the validation library's words, not this app's,
  and a field over 1 MiB gets a bare 400 from the framework.
- **The three severities are written out** as options in two forms; a fourth would
  have to be added to both by hand.

## 4. What comes next, with more time

1. A grounding history per aircraft ("grounded from Tuesday 09:00 to Wednesday
   14:00"). The log already holds it.
2. The withdrawal event.
3. A labeled set for the severity suggestions and a set of fleet questions whose
   answers are known, since nothing measures either.
4. Keeping a refused form's values.
5. Sign-in, so a name in the history is an identity, and with it inspector sign-off and
   deferral limits.

## 5. How I used AI

**Before the clock**, with an AI assistant's help, I chose the stack and probed it
against this repository's gates (Ruff with every rule, three type checkers, 100% branch
coverage, mutation testing), and wrote `docs/build-plan.md`: the product calls with a
default for each, the module design, the sample data, the order of work and the cut
line. The plan records probes dated 2026-11-19 and 2026-11-24 and a timing rehearsal
that was stopped and discarded. It is committed unchanged, so the repository shows what
I started from. No application code existed when the clock started.

**On the clock**, a coding agent (Claude Code) wrote all of the application code, the
tests and these documents in one session, whose log is submitted with this. What I did:

- I had it read the brief and criticize the plan before building. It proposed four
  changes and one new call, which I accepted; section 1 lists them.
- I confirmed or flipped each product call.
- I set the process: one pull request per stage; checks and mutation testing green
  before each push; a design review and a correctness review of each pull request by
  separate agent runs that see the code and not the author's reasoning; a second
  review after any severe finding; merge only after that.
- I corrected lint and typing problems I saw as it worked.
- With about half an hour left I asked for a better-looking frontend. The pages
  already existed, so the agent restyled them (#9) and checked the result from
  headless-browser screenshots in both color schemes.
- With these documents merged and about twenty-five minutes left, I asked for the
  fleet questions after all (#10). It had one review round like the rest.

What the reviews changed, since that is where the agent's first drafts were wrong:

- The web PR (#6) took three rounds. The first found two inputs that crashed a page (a
  past time outside the years a date can hold, and a write-up number past 64 bits) and
  rules copied into the templates. The agent's fix for the copies left new copies, and
  the second round found them. At that point it stopped patching and moved every such
  decision out of the templates into typed code; a third check found one more, fixed
  the same way. That cost the fleet-questions feature its place in the plan's order.
- The suggestion PR (#7): both reviews found that the form's carried suggestion was
  trusted whole, so a suggestion could be recorded against a description the model
  never saw. The app now seals each suggestion to its description.
- The fleet-questions PR (#10): the review found that what the tools returned never
  named a status or a state, so a cleared aircraft reached the model as an empty
  record. Each now carries its name. One design finding was left for time: the web
  layer works out each write-up's state and each aircraft's status for the tools,
  where the tools could do it from the store's own values.

- These documents: a separate run checked the README's walk-through and sections 2
  to 4 here against the running app. It found the walk-through's past view leaving
  out a grounded aircraft and two limits described loosely; all three are corrected.

What I would not claim: that the agent's output was right the first time, or that the
suggestion feature or the fleet questions have been measured. The reviews above are other runs of the same
model family, not an independent person's review. The key for the model is in a local
`.env` the agent was told never to read; no test calls the real model, and the agent
never did. Tests of both features run against scripted stand-ins for the model.
