"""Current withdrawal link inputs and optional response links."""

from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from ..._core.serialization import RequestModel, RequestMoney
from ._base import _ResponseModel


class WithdrawalLinkRequest(RequestModel):
    """Link input, separate from a direct withdrawal or its caller ID.

    Set platform only when supplied by xRocket. Network is required even though
    the OAS property has a default; amounts are serialized without rounding.
    """

    model_config = ConfigDict(alias_generator=to_camel, strict=True)

    network: Literal["TON", "BSC", "ETH", "BTC", "TRX", "SOL"]
    address: str = Field(max_length=100)
    asset: str
    amount: RequestMoney
    comment: str | None = Field(default=None, max_length=50)
    platform: str | None = None

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        # Optional properties can be omitted; Current does not mark them nullable.
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} must be omitted instead of set to None")
        return self


class WithdrawalLink(_ResponseModel):
    """Links returned by Current; no individual link is guaranteed to be present."""

    telegram_bot_link: str | None = None
    telegram_mini_app_link: str | None = None
    web_link: str | None = None

    @field_validator("telegram_bot_link", "telegram_mini_app_link", "web_link")
    @classmethod
    def _present_link(cls, value: str | None) -> str:
        # Missing is allowed, while a present link retains the OAS string type.
        if value is None:
            raise ValueError("Present withdrawal links must be strings, not null")
        return value
