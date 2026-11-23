"""A model derived from the base is frozen and rejects undeclared fields."""

import pytest
from pydantic import ValidationError

from airworthy.model import Model

pytestmark = pytest.mark.unit


class Point(Model):
    """A model with one field, to test the base through."""

    x: int


def test_a_model_is_frozen() -> None:
    point = Point(x=1)
    # Through setattr, so the type checkers, which reject the assignment, don't see it.
    field = "x"
    with pytest.raises(ValidationError, match="frozen"):
        setattr(point, field, 2)


def test_a_model_rejects_an_undeclared_field() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _ = Point.model_validate({"x": 1, "y": 2})
