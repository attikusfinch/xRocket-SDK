"""Payout responses with exact amounts and optional webhook settings."""

from typing import Any

from ._base import Money, _ResponseModel


class PayoutCallback(_ResponseModel):
    callback_url: str | None = None
    payload: dict[str, Any] | None = None


class Payout(_ResponseModel):
    payout_id: str
    target: str
    target_type: str
    asset: str
    amount: Money
    status: str
    client_payout_id: str | None = None
    description: str | None = None
    callback: PayoutCallback | None = None
