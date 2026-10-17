"""Explicit Current Pay withdrawal inputs, separate from response records."""

from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from ..._core.serialization import RequestModel, RequestMoney


class _WithdrawalRequestModel(RequestModel):
    model_config = ConfigDict(alias_generator=to_camel, strict=True)

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        # Optional OAS properties can be omitted, but none are nullable.
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} must be omitted instead of set to None")
        return self


class WithdrawalCallbackRequest(_WithdrawalRequestModel):
    """Optional withdrawal webhook override and caller-supplied JSON object."""

    callback_url: str | None = Field(default=None, max_length=500)
    payload: dict[str, Any] | None = None


class WithdrawalCreateRequest(_WithdrawalRequestModel):
    """Withdrawal input with exact money and a required caller-owned ID.

    Save the ID before sending. Create permits up to 150 characters, but
    ``retrieve(client_withdrawal_id=...)`` accepts only 1–100 (PAY-016).
    The SDK never generates, changes or truncates the caller's ID.
    """

    client_withdrawal_id: str = Field(max_length=150)
    network: Literal["TON", "BSC", "ETH", "BTC", "TRX", "SOL"]
    address: str = Field(max_length=100)
    asset: str
    amount: RequestMoney
    comment: str | None = Field(default=None, max_length=50)
    callback: WithdrawalCallbackRequest | None = None
