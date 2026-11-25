"""Suite-wide rules: every test declares exactly one surface marker.

The surfaces are registered here, the one place they are listed.

Also gives a session a temporary root of its own when `basetemp_per_session` is on,
as pyproject.toml's [tool.mutmut] sets it for mutmut's parallel sessions.

And runs the suite in a time zone that is not UTC, so code that reads the machine's
zone where it should read UTC lands on another day and fails a test.
"""

import os
import shutil
import tempfile
import time
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# The surfaces a test can exercise, each with what it promises.
SURFACE_MARKERS: Final[Mapping[str, str]] = {
    "unit": "fast, in-process, no I/O beyond tmp_path",
    "integration": "crosses a process, network or real service boundary",
    "smoke": "end-to-end check of the installed package or its public API",
}

# Nine hours ahead of UTC all year: a different calendar day for nine hours in every 24.
SUITE_TIME_ZONE: Final = "Asia/Tokyo"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the `basetemp_per_session` ini option."""
    parser.addini(
        "basetemp_per_session",
        "Give the session a temporary root of its own, removed when it ends.",
        type="bool",
        default=False,
    )


def pytest_configure(config: pytest.Config) -> None:
    """Set the suite's time zone, register the markers, apply `basetemp_per_session`.

    With `basetemp_per_session` on, the session gets its own `--basetemp`: sessions
    that share pytest's temporary root race each other's cleanup of it, which fails a
    session no test failed. A conftest's hook runs before the builtin tmpdir plugin's,
    which reads `--basetemp`.
    """
    os.environ["TZ"] = SUITE_TIME_ZONE
    time.tzset()
    for name, promise in SURFACE_MARKERS.items():
        config.addinivalue_line("markers", f"{name}: {promise}")
    if config.getini("basetemp_per_session"):
        basetemp = Path(tempfile.mkdtemp(prefix="pytest-"))
        config.option.basetemp = basetemp
        config.add_cleanup(partial(shutil.rmtree, basetemp, ignore_errors=True))


def pytest_collection_modifyitems(items: Sequence[pytest.Item]) -> None:
    """Reject any test that doesn't carry exactly one surface marker.

    Declare it once per module with `pytestmark = pytest.mark.unit` (or another
    surface), so a run can select a surface with `-m`.

    Raises:
        pytest.UsageError: If a collected test has no surface marker or more than one.
    """
    surfaces = {
        item: {mark.name for mark in item.iter_markers()} & SURFACE_MARKERS.keys()
        for item in items
    }
    wrong = [
        f"{item.nodeid}: {sorted(found) or 'none'}"
        for item, found in surfaces.items()
        if len(found) != 1
    ]
    if wrong:
        listing = "\n  ".join(wrong)
        msg = (
            f"each test needs exactly one surface marker of {sorted(SURFACE_MARKERS)} "
            f"(set `pytestmark` in its module):\n  {listing}"
        )
        raise pytest.UsageError(msg)
