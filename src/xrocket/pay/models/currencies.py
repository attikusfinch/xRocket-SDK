"""Supported currency and network response models."""

from ._base import _ResponseModel


class CurrencyNetwork(_ResponseModel):
    code: str


class Currency(_ResponseModel):
    code: str
    title: str
    kind: str
    networks: list[CurrencyNetwork]
