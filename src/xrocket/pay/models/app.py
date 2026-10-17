"""Application identity and balance response models."""

from ._base import Money, _ResponseModel


class AppInfo(_ResponseModel):
    id: str
    name: str


class Balance(_ResponseModel):
    asset: str
    balance: Money
    available: Money
    holds: Money


class AppBalances(_ResponseModel):
    balances: list[Balance]
