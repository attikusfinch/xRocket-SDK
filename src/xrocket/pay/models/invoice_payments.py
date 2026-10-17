"""Invoice payments, typed transactions, and their distinct cursor page."""

from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, Discriminator, Tag, field_validator

from ._base import Money, _ResponseModel


class InvoicePaymentPayer(_ResponseModel):
    email: str | None = None
    telegram_id: str | None = None
    telegram_username: str | None = None


class InvoiceBlockchainDetails(_ResponseModel):
    network: str
    tx_hash: str
    amount: Money
    currency: str
    status: str


class _InvoiceTransaction(_ResponseModel):
    id: str
    status: str
    created_at: AwareDatetime
    pay_amount: Money | None = None
    pay_currency: str | None = None
    receive_amount: Money | None = None
    receive_currency: str | None = None
    comment: str | None = None
    payer: InvoicePaymentPayer | None = None
    finalized_at: AwareDatetime | None = None


class InvoiceInternalTransaction(_InvoiceTransaction):
    type: Literal["internal"]


class InvoiceBlockchainTransaction(_InvoiceTransaction):
    type: Literal["blockchain"]
    tx: InvoiceBlockchainDetails | None = None


class UnknownInvoiceTransaction(_ResponseModel):
    """A future transaction type whose remaining fields retain their wire values."""

    type: str

    @field_validator("type")
    @classmethod
    def _unknown_type(cls, value: str) -> str:
        if value in ("internal", "blockchain"):
            raise ValueError("Known transaction types must use their typed response models")
        return value


def _transaction_type(value: Any) -> str | None:
    transaction_type = (
        value.get("type") if isinstance(value, dict) else getattr(value, "type", None)
    )
    if not isinstance(transaction_type, str):
        return None
    if transaction_type in ("internal", "blockchain"):
        return transaction_type
    return "unknown"


_Transaction = Annotated[
    Annotated[InvoiceInternalTransaction, Tag("internal")]
    | Annotated[InvoiceBlockchainTransaction, Tag("blockchain")]
    | Annotated[UnknownInvoiceTransaction, Tag("unknown")],
    Discriminator(_transaction_type),
]


class InvoicePayment(_ResponseModel):
    status: str
    pay_amount: Money
    pay_currency: str
    receive_amount: Money
    receive_currency: str
    transactions: list[_Transaction]
    id: str | None = None
    finalized_at: AwareDatetime | None = None


class InvoicePaymentPagination(_ResponseModel):
    next: str | None


class InvoicePaymentPage(_ResponseModel):
    items: list[InvoicePayment]
    pagination: InvoicePaymentPagination
