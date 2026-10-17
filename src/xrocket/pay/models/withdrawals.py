"""Withdrawal reads and quotas, keeping monetary and numeric precision separate."""

from typing import Annotated, Any

from pydantic import Field, StrictInt

from ._base import Money, _ResponseModel


class WithdrawalCallback(_ResponseModel):
    callback_url: str | None = None
    payload: dict[str, Any] | None = None


class Withdrawal(_ResponseModel):
    withdrawal_id: str
    network: str
    address: str
    asset: str
    amount: Money
    status: str | None = None
    comment: str | None = None
    tx_hash: str | None = None
    tx_link: str | None = None
    callback: WithdrawalCallback | None = None


class WithdrawalQuotas(_ResponseModel):
    withdraw_min_size: Money
    withdraw_fee: Money
    withdraw_fee_asset: str
    precision: StrictInt | Annotated[float, Field(strict=True, allow_inf_nan=False)]
