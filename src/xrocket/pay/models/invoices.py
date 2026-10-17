"""Invoice responses and their nested objects."""

from typing import Any

from pydantic import AwareDatetime, field_validator

from ._base import Money, _ResponseModel


class InvoiceCallback(_ResponseModel):
    callback_url: str | None = None
    payload: dict[str, Any] | None = None


class InvoiceURL(_ResponseModel):
    success_url: str | None = None
    cancel_url: str | None = None


class InvoiceCustomer(_ResponseModel):
    id: str | None = None
    email: str | None = None
    telegram_id: str | None = None
    telegram_username: str | None = None


class InvoiceLinks(_ResponseModel):
    telegram_bot_link: str
    telegram_mini_app_link: str | None = None
    web_link: str | None = None


class Invoice(_ResponseModel):
    id: str
    price_currency: str
    created_at: AwareDatetime
    status: str
    links: InvoiceLinks
    price_amount: Money | None = None
    min_payment: Money | None = None
    pay_currencies: list[str] | None = None
    client_invoice_id: str | None = None
    description: str | None = None
    expires_in: int | None = None
    expires_at: AwareDatetime | None = None
    callback: InvoiceCallback | None = None
    url: InvoiceURL | None = None
    customer: InvoiceCustomer | None = None


class InvoicePaymentAddress(_ResponseModel):
    """Created deposit address and its expiry, with an optional exact minimum."""

    address: str
    pay_currency: str
    pay_network: str
    expires_at: AwareDatetime
    min_amount: Money | None = None

    @field_validator("min_amount")
    @classmethod
    def _present_minimum(cls, value: Money | None) -> Money:
        # OAS allows omission, but does not declare this field nullable.
        if value is None:
            raise ValueError("Present minAmount must be an amount, not null")
        return value
