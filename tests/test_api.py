"""The package's facade lists every public name it offers."""

from typing import TYPE_CHECKING, Final

import pytest

import airworthy

if TYPE_CHECKING:
    from collections.abc import Mapping

pytestmark = pytest.mark.smoke

PACKAGE: Final = airworthy.__name__


def _defined_in_package(value: object) -> bool:
    """Tell whether `value` is a function, class or instance from the package's code."""
    module: object = getattr(value, "__module__", None)
    return isinstance(module, str) and module.partition(".")[0] == PACKAGE


def test_the_facade_lists_every_public_function_and_class() -> None:
    # Ruff's undefined-export checks the other direction: each listed name exists.
    # vars() returns dict[str, Any]; the annotation keeps that Any out of the loop,
    # which pyrefly's explicit-any-use reports from pyrefly 1.5.
    namespace: Mapping[str, object] = vars(airworthy)
    offered = {
        name
        for name, value in namespace.items()
        if not name.startswith("_") and _defined_in_package(value)
    }
    unlisted = sorted(offered - set(airworthy.__all__))
    assert not unlisted, (
        f"{PACKAGE} offers {unlisted} without listing them in __all__: list each "
        "public name, or import it under a leading underscore"
    )
