"""Command output. Every command prints one pretty-printed JSON value."""

import json
from typing import Any

from pydantic import BaseModel


def emit(value: BaseModel | list[Any] | dict[str, Any] | None) -> None:
    if value is None:
        return

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=True)

    print(json.dumps(value, indent=2))
