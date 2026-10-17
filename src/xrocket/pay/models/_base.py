"""Shared Pay response configuration and exact decimal amounts."""

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise ValueError("Money must be a decimal string, integer, or Decimal; floats are rejected")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid decimal amount") from None
    if not result.is_finite():
        raise ValueError("Money must be finite")
    return result


Money = Annotated[Decimal, BeforeValidator(_decimal)]


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True, alias_generator=to_camel)
