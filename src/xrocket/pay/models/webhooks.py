"""Current webhook DTOs. Constructing a DTO does not authenticate a delivery."""

import re
from copy import deepcopy
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BeforeValidator, Field, PrivateAttr, StrictStr, model_validator

from ._base import _ResponseModel
from .cheques import Cheque
from .invoice_payments import InvoiceInternalTransaction, InvoicePayment
from .invoices import Invoice
from .payouts import Payout
from .withdrawals import Withdrawal


def _timestamp_string(value: Any) -> Any:
    # JSON timestamps follow the date-time string schema, never epoch numbers.
    # Aware datetime instances remain useful for explicit DTO construction.
    if not isinstance(value, (str, datetime)):
        raise ValueError("Webhook timestamp must be a date-time string")
    if isinstance(value, str) and re.match(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt ]", value) is None:
        raise ValueError("Webhook timestamp must be a date-time string")
    return value


def _date_fields(value: Any, model: type[_ResponseModel], names: tuple[str, ...]) -> None:
    """Guard effective known wire values before REST DTO datetime coercion.

    Alias precedence matches _ResponseModel: a Python-name duplicate beside a
    wire alias is an extra, so it must remain opaque. Missing/null handling and
    aware date-time parsing stay with the existing DTO validators.
    """
    if isinstance(value, dict):
        for name in names:
            alias = model.model_fields[name].alias or name
            raw_date = value[alias] if alias in value else value.get(name)
            if raw_date is not None:
                _timestamp_string(raw_date)


def _invoice_dates(value: Any) -> Any:
    _date_fields(value, Invoice, ("created_at", "expires_at"))
    return value


def _payment_dates(value: Any) -> Any:
    _date_fields(value, InvoicePayment, ("finalized_at",))
    if isinstance(value, dict) and isinstance(value.get("transactions"), list):
        for transaction in value["transactions"]:
            if isinstance(transaction, dict) and transaction.get("type") in (
                "internal",
                "blockchain",
            ):
                # Both known transaction DTOs share these fields. Future types
                # retain raw fields; their date-looking values are not interpreted.
                _date_fields(
                    transaction, InvoiceInternalTransaction, ("created_at", "finalized_at")
                )
    return value


class _WebhookModel(_ResponseModel):
    def __repr_args__(self) -> list[tuple[str | None, Any]]:
        # Suppress every field and extra, including untrusted ids/type/event names.
        # Both BaseModel.__repr__ and __str__ use this hook.
        return [("payload", "<redacted>")]


class InvoiceStatusChangedWebhookData(_WebhookModel):
    event: Literal["invoice_status_changed"]
    invoice: Annotated[Invoice, BeforeValidator(_invoice_dates)]


class PaymentStatusChangedWebhookData(_WebhookModel):
    event: Literal["payment_status_changed"]
    invoice: Annotated[Invoice, BeforeValidator(_invoice_dates)]
    payment: Annotated[InvoicePayment, BeforeValidator(_payment_dates)]


class _WebhookEnvelope(_WebhookModel):
    id: StrictStr
    timestamp: Annotated[AwareDatetime, BeforeValidator(_timestamp_string)]
    type: StrictStr
    _raw_body: bytes | None = PrivateAttr(default=None)
    _raw_payload: dict[str, Any] | None = PrivateAttr(default=None)

    @property
    def raw_body(self) -> bytes:
        """Exact authenticated bytes, available only after verify_and_decode_webhook.

        Explicit access may expose sensitive data. DTO constructors/model_validate
        never authenticate inputs and cannot populate this private snapshot.
        """
        if self._raw_body is None:
            raise RuntimeError("Raw webhook bytes require verify_and_decode_webhook")
        return self._raw_body

    @property
    def raw_payload(self) -> dict[str, Any]:
        """A separate copy of the authenticated JSON, with exact Decimal numbers.

        This preserves original wire keys, unknown fields and explicit nulls,
        independently of subsequent DTO mutations. Explicit access is sensitive.
        """
        if self._raw_payload is None:
            raise RuntimeError("Raw webhook payload requires verify_and_decode_webhook")
        return deepcopy(self._raw_payload)


class InvoiceWebhook(_WebhookEnvelope):
    type: Literal["invoice"]
    data: Annotated[
        InvoiceStatusChangedWebhookData | PaymentStatusChangedWebhookData,
        Field(discriminator="event"),
    ]


class ChequeWebhook(_WebhookEnvelope):
    # Current Cheque/Payout/Withdrawal and their declared nested DTOs have no
    # date-time fields. Date-looking extras/callback payloads remain raw values.
    type: Literal["cheque"]
    data: Cheque


class PayoutWebhook(_WebhookEnvelope):
    type: Literal["payout"]
    data: Payout


class WithdrawalWebhook(_WebhookEnvelope):
    type: Literal["withdrawal"]
    data: Withdrawal


class UnknownWebhook(_WebhookEnvelope):
    """A future envelope type or invoice event, without financial interpretation."""

    data: Any

    @model_validator(mode="after")
    def _future_event_only(self) -> "UnknownWebhook":
        if self.type in ("cheque", "payout", "withdrawal"):
            raise ValueError("Known webhook types require their typed DTOs")
        if self.type == "invoice":
            if not isinstance(self.data, dict) or not isinstance(self.data.get("event"), str):
                raise ValueError("Invoice webhook requires a string event")
            if self.data["event"] in ("invoice_status_changed", "payment_status_changed"):
                raise ValueError("Known invoice events require their typed DTOs")
        return self


WebhookEvent = InvoiceWebhook | ChequeWebhook | PayoutWebhook | WithdrawalWebhook | UnknownWebhook
