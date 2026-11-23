# Working in airworthy

Conventions for anyone, human or agent, changing this project. `CLAUDE.md` imports
this file, so Claude Code reads it too.

## Commands

```
scripts/check                   # every check, as CI runs it; run before each push
scripts/check --list            # the checks, by step name
scripts/check pytest -x -k <n>  # one step, with arguments for its tool
scripts/mutation                # mutation testing (CI: mutation.yaml)
```

Always run tools through `uv run` (the scripts do), never a bare `python` or `pip`.
`uv.lock` is committed and every check runs locked, failing when the lock no longer
matches, so change dependencies with `uv add` / `uv remove`, never by editing the lock.

A script with PEP 723 metadata commits its own lock beside it, `<script>.py.lock`: ty
checks the script against the environment that lock pins and fails without it, so run
`uv lock --script <script>` after changing the script's metadata.

## The ways past a gate

The gates are the steps of `scripts/check`, plus `scripts/mutation`. These have a
sanctioned way past; every other gate has none, so fix what it reports.

| gate | config | the only way past it |
|---|---|---|
| Ruff, every rule, preview on | `[tool.ruff]` | `# ruff: ignore[rule-name] — reason` at one site; a `[tool.ruff.lint.per-file-ignores]` entry only for one decision across many files |
| mypy strict, no explicit `Any`, and in `src/` no expression or decorated function whose type contains `Any` | `[tool.mypy]` | a typed fix; `# type: ignore[code]` with a reason as a last resort |
| ty, every rule on | `[tool.ty]` | a typed fix; `# ty: ignore[rule]` with a reason as a last resort, since ty honors no other checker's comment |
| pyrefly, every rule on but `implicit-bool` | `[tool.pyrefly]` | a typed fix; `# pyrefly: ignore[kind]` with a reason as a last resort, since pyrefly honors no other checker's comment |
| cognitive complexity ceiling | `[tool.complexipy]` | `complexipy --snapshot-create`, committed as `complexipy-snapshot.json`, which shrinks as functions improve |
| import boundaries | `[tool.importlinter]` | a contract changed in review |
| 100% branch coverage | `[tool.coverage]` | `exclude_lines`' fixed list, nothing else: coverage's `# pragma: no cover` and `# pragma: no branch` don't apply |
| mutation testing, no survivors | `[tool.mutmut]` | `# pragma: no mutate — reason` on the line of an equivalent mutant; it skips every mutant on that line |

`# noqa` never appears: preview Ruff rejects it in favor of `# ruff: ignore[...]`,
and an unused suppression fails the build.

Annotate every parameter but `self` and `cls`, every return, and a name whose value
doesn't give its type (`names: list[str] = []`, an attribute first set to `None`): the
gate fails one left bare. Every other name takes its type from its right-hand side, so
`root = Path("src")` and `self.root = root` carry no annotation. No step counts
annotations: `pyrefly coverage check` is not part of the gate.

In `src/`, cast a library's `Any` once, in the code that wraps that library, so
everything past the wrapper sees a real type.
For Pydantic that code is a method on the base model in `model.py`, such as one
returning `model_dump()` as `dict[str, object]`.
Cast with `cast("dict[str, object]", json.loads(text))`
rather than annotating the assignment, which mypy accepts but ty rejects as
`unsound-assignment`.
A decorator whose type contains `Any`, such as `functools.cache`, gets a typed wrapper
of its own, applied in its place.

A surviving mutant is a change the tests don't notice and mutmut's type check doesn't
reject: mutmut runs mypy over the mutants first (`type_check_command`) and counts one
it rejects as caught, but for a `misc` error, which that check leaves to the tests.
Remove a survivor in this order:

1. A test, when the change is to behavior a caller sees, an error's text included.
2. A tighter type, when the value has a closed set of legal values (a `Literal`, an
   enum) that the mutant leaves.
3. Deleting the code, when nothing reads what it computes.
4. Reshaping the code, when the mutant is in a form a test can't reach: end an
   exhaustive `match` with `assert_never` (coverage leaves that line out, so mutmut
   does too), drop an arm that does what falling through would, and build a table as a
   literal or on first use rather than with a call at import, which runs before mutmut
   switches a mutant on.
5. The pragma, only for an equivalent mutant: one that no input can tell apart.

While working on one, `uv run mutmut run <name>` retests just that mutant against
the current code and tests, and `uv run mutmut browse` lists the rest. mutmut keeps
each other mutant's earlier result until its function changes, so take the verdict
from `scripts/mutation`, which starts from scratch.

## Layout and import direction

The `layers` contract in `[tool.importlinter]` is exhaustive, so a new top-level
module of `src/airworthy/` fails `scripts/check imports` until it is listed
there, highest first: `layers = ["cli", "adapters", "core"]`.

Name layers by what the code touches (infrastructure, Pure, adapters, ...), import
downward at runtime and upward only under `if TYPE_CHECKING:`, and go through a
subpackage's facade from outside it. Add a `protected` contract for a facade that
matters.

Names: modules of 2-9 characters and no underscores in package names; the top-level
package name may run to 10 characters.
Data models: `@dataclass(slots=True, kw_only=True, frozen=True)`, or frozen Pydantic
models. Ruff and mypy are configured for Pydantic. A base model defined in another
module goes into Ruff's `runtime-evaluated-base-classes`.

## Tests

Tests mirror `src/` (`tests/<subpackage>/`, repo-wide invariants in `tests/_meta/`),
no `__init__.py` under `tests/`, one surface marker per module from those
`tests/conftest.py` registers (`pytestmark = pytest.mark.unit`, say; the conftest
rejects a test without exactly one), tests share code through fixtures and import
neither another test module nor a conftest (Ruff bans both), and tests reach code only
through public seams: pass collaborators as parameters, never patch a module (Ruff
bans `unittest.mock.patch`).

A test module's docstring says what its unit promises, and a test's name states the
behavior it pins. Give a test a docstring only for what its name can't hold: why the
behavior matters, the issue a regression test pins, or a setup that would surprise a
reader. A docstring that restates the name says nothing, so Ruff asks for none on a
test. A helper serves only its own test module, so its name starts with `_`.

## Python skills

Where the `python-idioms` Claude Code plugin is installed, its skills hold the detail
behind each kind of Python question below: `python-idioms:python-baseline` is the
foundation, with one skill per idiom. Open the skill a question names before writing or
reviewing that kind of code. Where a skill and this project differ, this file, the
config in `pyproject.toml` and the code's existing style win. Without the plugin, this
file and the config are the whole contract.

| question | skill | this file |
|---|---|---|
| toolchain, Ruff suppressions, `per-file-ignores` | `python-baseline` § Toolchain | § Commands, § The ways past a gate |
| what is public, layer imports, package facades | `visibility` (`references/package-facades.md`) | § Layout and import direction |
| module and package names | `module-naming` | § Layout and import direction |
| dataclass and Pydantic field declarations | `model-fields` | § Layout and import direction |
| frozen models | `frozen-models` | § Layout and import direction |
| errors and cleanup | `error-handling` | |
| logging | `logging` | |
| annotations and empty collections | `inferred-types` | |
| docstrings | `docstrings` | § Tests, for a test's docstring |
| test layout, markers, fixtures, seams | `pytest-layout` | § Tests |

## Versions and releases

The version comes from git tags (`hatch-vcs`); `pyproject.toml` holds none. A commit
tagged `v1.2.0` builds 1.2.0, and any other commit a development version past the last
tag. The package is never published: its `Private :: Do Not Upload` classifier
makes PyPI refuse it.

## Git and pull requests

- Branches are `<type>/<kebab-description>` with a Conventional Commits type.
- PR titles are Conventional Commits too (`pr-title-lint.yaml`); a squash merge uses
  the title as the commit message.
- Open PRs as drafts; CI runs when one is marked ready.

## Updating from the template

This project was generated from `gh:willfrey/copier-python`;
`.copier-answers.yaml` records the version and answers. Pull template changes with
`uvx copier update --trust --answers-file .copier-answers.yaml` (`copier update`
looks for `.copier-answers.yml` without the flag), and review the diff like any other
change.
