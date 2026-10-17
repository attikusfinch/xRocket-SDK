"""Explicit invoice reads and request-backed creation and deletion."""

from pydantic import TypeAdapter

from xrocket._core.transport import AsyncTransport, Query, SyncTransport
from xrocket.pay.models import CursorPage, Invoice, InvoiceCreateRequest, InvoicePaymentPage

_INVOICE = TypeAdapter(Invoice)
_PAGE = TypeAdapter(CursorPage[Invoice])
_PAYMENTS_PAGE = TypeAdapter(InvoicePaymentPage)


def _validate_limit(limit: int | None) -> None:
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000
    ):
        raise ValueError("limit must be an integer between 1 and 1000")


def _list_params(
    asset: str | None,
    fiat: str | None,
    ids: list[str] | None,
    status: str | None,
    cursor: str | None,
    limit: int | None,
) -> Query:
    _validate_limit(limit)
    params: Query = []
    for name, value in (
        ("asset", asset),
        ("fiat", fiat),
        ("status", status),
        ("cursor", cursor),
        ("limit", limit),
    ):
        if value is not None:
            params.append((name, value))
    if ids is not None:
        params.extend(("ids", identifier) for identifier in ids)
    return params


def _retrieve_params(invoice_id: str | None, client_invoice_id: str | None) -> Query:
    if not invoice_id and not client_invoice_id:
        raise ValueError("invoice_id or client_invoice_id is required")
    params: Query = []
    for name, value in (("invoiceId", invoice_id), ("clientInvoiceId", client_invoice_id)):
        if value is not None:
            if not isinstance(value, str) or not value or len(value) > 100:
                raise ValueError("Invoice identifiers must contain 1 to 100 characters")
            params.append((name, value))
    return params


def _payments_params(
    invoice_id: str | None,
    client_invoice_id: str | None,
    cursor: str | None,
    limit: int | None,
) -> Query:
    params = _retrieve_params(invoice_id, client_invoice_id)
    _validate_limit(limit)
    if cursor is not None:
        params.append(("cursor", cursor))
    if limit is not None:
        params.append(("limit", limit))
    return params


class InvoicesResource:
    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def create(self, *, request: InvoiceCreateRequest) -> Invoice:
        """Create an invoice from an explicit request DTO; no automatic retries."""
        if not isinstance(request, InvoiceCreateRequest):
            raise TypeError("request must be an InvoiceCreateRequest")
        return self._transport.request(
            "POST", "/api/v1/invoices", _INVOICE, success_statuses=(200,), body=request
        )

    def delete(
        self,
        *,
        invoice_id: str | None = None,
        client_invoice_id: str | None = None,
    ) -> None:
        """Delete by either identifier; both are forwarded when supplied."""
        return self._transport.request(
            "DELETE",
            "/api/v1/invoice",
            None,
            success_statuses=(200,),
            params=_retrieve_params(invoice_id, client_invoice_id),
        )

    def list(
        self,
        *,
        asset: str | None = None,
        fiat: str | None = None,
        ids: list[str] | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> CursorPage[Invoice]:
        return self._transport.get(
            "/api/v1/invoices",
            _PAGE,
            params=_list_params(asset, fiat, ids, status, cursor, limit),
        )

    def retrieve(
        self,
        *,
        invoice_id: str | None = None,
        client_invoice_id: str | None = None,
    ) -> Invoice:
        return self._transport.get(
            "/api/v1/invoice",
            _INVOICE,
            params=_retrieve_params(invoice_id, client_invoice_id),
        )

    def payments(
        self,
        *,
        invoice_id: str | None = None,
        client_invoice_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> InvoicePaymentPage:
        return self._transport.get(
            "/api/v1/invoice/payments",
            _PAYMENTS_PAGE,
            params=_payments_params(invoice_id, client_invoice_id, cursor, limit),
        )


class AsyncInvoicesResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def create(self, *, request: InvoiceCreateRequest) -> Invoice:
        """Create an invoice from an explicit request DTO; no automatic retries."""
        if not isinstance(request, InvoiceCreateRequest):
            raise TypeError("request must be an InvoiceCreateRequest")
        return await self._transport.request(
            "POST", "/api/v1/invoices", _INVOICE, success_statuses=(200,), body=request
        )

    async def delete(
        self,
        *,
        invoice_id: str | None = None,
        client_invoice_id: str | None = None,
    ) -> None:
        """Delete by either identifier; both are forwarded when supplied."""
        return await self._transport.request(
            "DELETE",
            "/api/v1/invoice",
            None,
            success_statuses=(200,),
            params=_retrieve_params(invoice_id, client_invoice_id),
        )

    async def list(
        self,
        *,
        asset: str | None = None,
        fiat: str | None = None,
        ids: list[str] | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> CursorPage[Invoice]:
        return await self._transport.get(
            "/api/v1/invoices",
            _PAGE,
            params=_list_params(asset, fiat, ids, status, cursor, limit),
        )

    async def retrieve(
        self,
        *,
        invoice_id: str | None = None,
        client_invoice_id: str | None = None,
    ) -> Invoice:
        return await self._transport.get(
            "/api/v1/invoice",
            _INVOICE,
            params=_retrieve_params(invoice_id, client_invoice_id),
        )

    async def payments(
        self,
        *,
        invoice_id: str | None = None,
        client_invoice_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> InvoicePaymentPage:
        return await self._transport.get(
            "/api/v1/invoice/payments",
            _PAYMENTS_PAGE,
            params=_payments_params(invoice_id, client_invoice_id, cursor, limit),
        )
