"""Explicit testnet reads. Importing this module performs no requests."""

import os

import httpx

from xrocket.pay import AppBalances, AsyncPayClient, CursorPage, Invoice, PayClient


def read_sync(
    *,
    http_client: httpx.Client | None = None,
) -> tuple[AppBalances, CursorPage[Invoice]]:
    """Read balances and exactly one invoice page using a testnet application JWT."""
    with PayClient(
        api_token=os.environ["XROCKET_PAY_TESTNET_TOKEN"],
        environment="testnet",
        http_client=http_client,
    ) as client:
        balances = client.app.balances()
        page = client.invoices.list(limit=100)
        # A next page requires another explicit call with cursor=page.pagination.next.
        return balances, page


async def read_async(
    *,
    http_client: httpx.AsyncClient | None = None,
) -> tuple[AppBalances, CursorPage[Invoice]]:
    """Async equivalent; an injected HTTP client remains owned by its caller."""
    async with AsyncPayClient(
        api_token=os.environ["XROCKET_PAY_TESTNET_TOKEN"],
        environment="testnet",
        http_client=http_client,
    ) as client:
        balances = await client.app.balances()
        page = await client.invoices.list(limit=100)
        # A next page requires another explicit call with cursor=page.pagination.next.
        return balances, page
