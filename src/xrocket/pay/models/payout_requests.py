"""Explicit Current Pay single and mass payout inputs, separate from responses."""

from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from ..._core.serialization import RequestModel, RequestMoney


class _PayoutRequestModel(RequestModel):
    model_config = ConfigDict(alias_generator=to_camel, strict=True)

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        # Optional OAS properties can be omitted, but none are nullable.
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} must be omitted instead of set to None")
        return self


class PayoutCallbackRequest(_PayoutRequestModel):
    """Optional payout webhook override and caller-supplied JSON object."""

    callback_url: str | None = Field(default=None, max_length=500)
    payload: dict[str, Any] | None = None


class PayoutCreateRequest(_PayoutRequestModel):
    """Single payout input with exact money and an optional caller-owned ID.

    Save a stable ``client_payout_id`` before sending if you need to look up an
    unknown result after a timeout. The SDK never generates or changes this ID.
    """

    target: str = Field(max_length=100)
    target_type: Literal["user_id", "telegram_user_id", "telegram_username"]
    asset: str
    amount: RequestMoney
    client_payout_id: str | None = Field(default=None, max_length=50)
    description: str | None = None
    callback: PayoutCallbackRequest | None = None


class MassPayoutItemRequest(_PayoutRequestModel):
    """One batch item; asset belongs to the enclosing request.

    Only Telegram user IDs are accepted locally, following the operation prose
    while the wider schema enum remains unconfirmed (PAY-010).
    """

    target: str = Field(max_length=100)
    target_type: Literal["telegram_user_id"]
    amount: RequestMoney
    client_payout_id: str | None = Field(default=None, max_length=50)
    description: str | None = None
    callback: PayoutCallbackRequest | None = None


class MassPayoutCreateRequest(_PayoutRequestModel):
    """One batch, without an inferred size limit or automatic splitting.

    Save a distinct stable client ID per item if you need to correlate results.
    No minItems/maxItems is declared by Current OAS (PAY-009).
    """

    asset: str
    payouts: list[MassPayoutItemRequest]
