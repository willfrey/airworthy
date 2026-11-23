"""The base of the package's Pydantic models."""

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """A model that is frozen and rejects a field it doesn't declare."""

    model_config = ConfigDict(frozen=True, extra="forbid")
