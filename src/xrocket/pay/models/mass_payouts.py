"""Mass payout results retain separate successful and failed item collections."""

from typing import Annotated

from pydantic import Field, StrictInt, field_validator

from ._base import Money, _ResponseModel
from .payouts import Payout


class MassPayoutErrorReason(_ResponseModel):
    """Item problem details, independent of the enclosing HTTP 200 status."""

    type: str
    title: str
    status: StrictInt | Annotated[float, Field(strict=True, allow_inf_nan=False)]
    detail: str
    instance: str
    kind: str

    @field_validator("status", mode="before")
    @classmethod
    def _status_number(cls, value: object) -> int | float:
        # Even strict float validation accepts Decimal and numeric protocols.
        # Keep the JSON number kind instead of coercing another input type.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Item reason status must be a JSON number")
        return value


class MassPayoutError(_ResponseModel):
    """A failed item with its original correlation fields and problem details."""

    target: str
    target_type: str
    amount: Money
    reason: MassPayoutErrorReason
    client_payout_id: str | None = None
    description: str | None = None


class MassPayoutResult(_ResponseModel):
    """HTTP 200 may contain item failures; inspect both collections.

    Lists retain server order and identifiers. The API does not guarantee their
    positions match request positions, or return an index for failed items.
    """

    success_payouts: list[Payout]
    error_payouts: list[MassPayoutError]

    @property
    def has_errors(self) -> bool:
        """Whether the server reported any failed items."""
        return bool(self.error_payouts)

    @property
    def is_partial(self) -> bool:
        """Whether both successful and failed items were returned."""
        return bool(self.success_payouts and self.error_payouts)
