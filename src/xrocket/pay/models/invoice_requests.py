"""Explicit request DTOs for Current Pay invoices and their payment addresses."""

from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from ..._core.serialization import RequestModel, RequestMoney


class _InvoiceRequestModel(RequestModel):
    model_config = ConfigDict(alias_generator=to_camel, strict=True)

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> Self:
        # Optional OAS properties can be omitted, but none are nullable.
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} must be omitted instead of set to None")
        return self


class InvoiceCallbackRequest(_InvoiceRequestModel):
    """Optional invoice webhook override and caller-supplied JSON payload."""

    callback_url: str | None = Field(default=None, max_length=500)
    payload: dict[str, Any] | None = None


class InvoiceURLRequest(_InvoiceRequestModel):
    """Optional payer redirects after a successful or cancelled payment."""

    success_url: str | None = Field(default=None, max_length=500)
    cancel_url: str | None = Field(default=None, max_length=500)


class InvoiceCustomerRequest(_InvoiceRequestModel):
    """Optional customer identifiers attached to the invoice."""

    id: str | None = None
    email: str | None = None
    telegram_id: str | None = None
    telegram_username: str | None = None


class InvoiceCreateRequest(_InvoiceRequestModel):
    """Invoice create input with exact amounts and millisecond expiry.

    ``price_amount`` and ``min_payment`` are mutually exclusive. Both may be
    omitted: the upstream required list and missing-amount error conflict, so
    acceptance of that form remains a server decision (PAY-008).
    """

    price_currency: str
    price_amount: RequestMoney | None = None
    min_payment: RequestMoney | None = None
    num_payments: int | None = Field(default=None, ge=1, le=1_000_000)
    payout_currency: str | None = None
    pay_currencies: list[str] | None = None
    client_invoice_id: str | None = None
    description: str | None = Field(default=None, max_length=1000)
    expires_in: int | None = None
    callback: InvoiceCallbackRequest | None = None
    url: InvoiceURLRequest | None = None
    customer: InvoiceCustomerRequest | None = None
    data: dict[str, Any] | None = None
    platform_id: str | None = None

    @model_validator(mode="after")
    def _validate_amount_choice(self) -> Self:
        if self.price_amount is not None and self.min_payment is not None:
            raise ValueError("price_amount and min_payment are mutually exclusive")
        return self


class InvoiceCreatePaymentAddressRequest(_InvoiceRequestModel):
    """Network selection for creating an invoice payment address.

    Invoice identifiers belong to the resource method's query arguments.
    """

    pay_network: Literal["TON", "BSC", "ETH", "BTC", "TRX", "SOL"]
