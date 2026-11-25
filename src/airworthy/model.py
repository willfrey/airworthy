"""The base of the package's Pydantic models, and typed reads of what Pydantic gives."""

from typing import TYPE_CHECKING, TypedDict, cast

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic import ValidationError


class Model(BaseModel):
    """A model that is frozen and rejects a field it doesn't declare."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    def posted(self) -> dict[str, object]:
        """Give what the model holds, by name: for a form, the fields it posted."""
        return cast("dict[str, object]", self.model_dump())


class Fault(TypedDict):
    """One thing a validation refused: where it was, and why in Pydantic's words."""

    loc: tuple[int | str, ...]
    msg: str


def faults(error: ValidationError) -> Sequence[Fault]:
    """Give what a validation refused, in the order Pydantic found it."""
    return cast("Sequence[Fault]", error.errors())
