"""Explicit request DTOs and lossless JSON request serialization."""

import json
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer, SecretStr


def _request_money(value: Any) -> Decimal:
    if not isinstance(value, (Decimal, str)):
        raise ValueError("Request money must be a decimal string or Decimal")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid decimal amount") from None
    if not amount.is_finite():
        raise ValueError("Request money must be finite")
    return amount


RequestMoney = Annotated[
    Decimal,
    BeforeValidator(_request_money),
    PlainSerializer(str, return_type=str, when_used="json"),
]


class RequestModel(BaseModel):
    """Base for intentional outbound data; products supply their wire aliases."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        revalidate_instances="always",
    )


def _check_request_values(value: object, active: set[int]) -> None:
    # Reject invalid Unicode before creating JSON text. An encoding exception
    # would retain that entire text, including any intentionally revealed secret.
    if isinstance(value, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError("Request strings must not contain surrogate code points")
    if isinstance(value, BaseModel) and not isinstance(value, RequestModel):
        raise TypeError("Request payloads must not contain response models")
    if isinstance(value, (set, frozenset)):
        raise TypeError("Request payloads must not contain sets")
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("Request JSON numbers must be finite")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("Request decimal values must be finite")

    if isinstance(value, RequestModel):
        children = list(value.__dict__.values())
        if value.model_extra:
            children.extend(value.model_extra.values())
    elif isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("Request JSON object keys must be strings")
        children = [*value.keys(), *value.values()]
    elif isinstance(value, (list, tuple)):
        children = list(value)
    elif value is None or isinstance(value, (str, bool, int, float, Decimal, SecretStr)):
        return
    else:
        raise TypeError("Request payloads must contain JSON values or request models")

    identity = id(value)
    if identity in active:
        raise ValueError("Request payloads must not contain cycles")
    active.add(identity)
    try:
        for child in children:
            _check_request_values(child, active)
    finally:
        active.remove(identity)


def _revalidate_request_values(value: object) -> object:
    if isinstance(value, RequestModel):
        # A shallow copy preserves fields_set, unlike model_copy(update=...).
        # Normalize nested DTOs first: Pydantic does not revalidate models hidden
        # in Any or arbitrary JSON dictionaries during outer model validation.
        candidate = value.model_copy()
        for name, child in candidate.__dict__.items():
            candidate.__dict__[name] = _revalidate_request_values(child)
        if candidate.model_extra:
            for name, child in candidate.model_extra.items():
                candidate.model_extra[name] = _revalidate_request_values(child)
        validated = type(value).model_validate(candidate)
        # A custom model_construct(_fields_set=...) must not omit a validated
        # required wire field. Only this normalized clone gains those fields.
        validated.model_fields_set.update(
            name for name, field in type(validated).model_fields.items() if field.is_required()
        )
        return validated
    if isinstance(value, dict):
        return {key: _revalidate_request_values(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_revalidate_request_values(child) for child in value]
    if isinstance(value, tuple):
        return tuple(_revalidate_request_values(child) for child in value)
    return value


def serialize_request(model: RequestModel) -> bytes:
    """Validate a request again and encode its explicitly supplied JSON fields.

    Unset fields are omitted recursively, while explicit nulls and explicit
    defaults are retained. Response models require an intentional field mapping
    into a request DTO instead of being serialized as an outbound payload.
    """
    if not isinstance(model, RequestModel):
        raise TypeError("Request body must be a RequestModel")
    _check_request_values(model, set())
    validated = _revalidate_request_values(model)
    assert isinstance(validated, RequestModel)
    _check_request_values(validated, set())
    payload = validated.model_dump(
        mode="json",
        by_alias=True,
        exclude_unset=True,
        warnings="error",
        context={"request_wire": True},
    )
    _check_request_values(payload, set())
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
        "utf-8"
    )
