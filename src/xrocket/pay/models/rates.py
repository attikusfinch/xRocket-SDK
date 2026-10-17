"""Exchange rate response models."""

from ._base import Money, _ResponseModel


class Rate(_ResponseModel):
    currency: str
    rate: Money
