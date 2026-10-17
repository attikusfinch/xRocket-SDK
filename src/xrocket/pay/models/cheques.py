"""Cheque responses and their optional nested objects."""

from typing import Any

from ._base import _ResponseModel


class ChequeLinks(_ResponseModel):
    telegram_bot_link: str | None = None
    telegram_mini_app_link: str | None = None
    web_link: str | None = None


class ChequeCallback(_ResponseModel):
    callback_url: str | None = None
    payload: dict[str, Any] | None = None


class ChequeURL(_ResponseModel):
    success_url: str | None = None
    cancel_url: str | None = None


class Cheque(_ResponseModel):
    cheque_id: str
    asset: str
    links: ChequeLinks
    deleted: bool
    client_cheque_id: str | None = None
    description: str | None = None
    target_type: str | None = None
    target: str | None = None
    state: str | None = None
    callback: ChequeCallback | None = None
    url: ChequeURL | None = None
