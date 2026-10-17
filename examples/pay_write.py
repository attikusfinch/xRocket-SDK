"""Opt-in testnet invoice creation. Importing this module performs no writes."""

import os
from decimal import Decimal

import httpx

from xrocket.pay import AsyncPayClient, Invoice, InvoiceCreateRequest, PayClient


def create_invoice_sync(*, http_client: httpx.Client | None = None) -> Invoice:
    """Create once with an application-persisted ID; a timeout has an unknown outcome.

    The application owns the stable client invoice ID and reconciliation policy.
    Its presence is not a verified server idempotency guarantee. No retry or lookup
    is performed here. Call this function only when a testnet write is intended.
    """
    request = InvoiceCreateRequest(
        price_currency="USDT",
        price_amount=Decimal("1.2500"),
        client_invoice_id=os.environ["XROCKET_PAY_TESTNET_CLIENT_INVOICE_ID"],
        expires_in=300_000,  # Milliseconds.
    )
    with PayClient(
        api_token=os.environ["XROCKET_PAY_TESTNET_TOKEN"],
        environment="testnet",
        http_client=http_client,
    ) as client:
        return client.invoices.create(request=request)


async def create_invoice_async(*, http_client: httpx.AsyncClient | None = None) -> Invoice:
    """Async equivalent with the same caller-owned ID and unknown-outcome policy."""
    request = InvoiceCreateRequest(
        price_currency="USDT",
        price_amount=Decimal("1.2500"),
        client_invoice_id=os.environ["XROCKET_PAY_TESTNET_CLIENT_INVOICE_ID"],
        expires_in=300_000,
    )
    async with AsyncPayClient(
        api_token=os.environ["XROCKET_PAY_TESTNET_TOKEN"],
        environment="testnet",
        http_client=http_client,
    ) as client:
        return await client.invoices.create(request=request)
