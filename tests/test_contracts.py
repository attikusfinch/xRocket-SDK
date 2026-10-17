import inspect
import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from xrocket.pay import AsyncPayClient, PayClient

INVOICE = {
    "id": "inv-123",
    "priceCurrency": "USDT",
    "priceAmount": "12345678901234567890.123456789",
    "createdAt": "2026-10-17T08:00:00Z",
    "expiresAt": None,
    "status": "a_future_status",
    "links": {"telegramBotLink": "https://t.me/xRocket?start=inv_test"},
    "futureField": {"value": 1},
}

CASES = [
    ("app.info", "/api/v1/app-info", {}, {"id": "app-1", "name": "Test app"}),
    (
        "app.balances",
        "/api/v1/balances",
        {},
        {
            "balances": [
                {"asset": "USDT", "balance": "123.4500", "available": "100", "holds": "23.45"}
            ]
        },
    ),
    (
        "currencies.list",
        "/api/v1/currencies",
        {"kind": "crypto"},
        [{"code": "USDT", "title": "Tether", "kind": "crypto", "networks": [{"code": "TON"}]}],
    ),
    (
        "rates.get",
        "/api/v1/rates",
        {"base": "USD", "assets": ["BTC", "TON"]},
        [{"currency": "BTC", "rate": "99999.1234567890123456789"}],
    ),
    (
        "invoices.list",
        "/api/v1/invoices",
        {
            "asset": "USDT",
            "fiat": "USD",
            "ids": ["inv-123", "inv-456"],
            "status": "active",
            "cursor": "opaque+/= cursor",
            "limit": 100,
        },
        {"items": [INVOICE], "pagination": {"total": 3, "next": "next+/= cursor"}},
    ),
    (
        "invoices.retrieve",
        "/api/v1/invoice",
        {"invoice_id": "inv-123", "client_invoice_id": "order-123"},
        INVOICE,
    ),
]


async def invoke(client: Any, operation: str, kwargs: dict[str, Any]) -> Any:
    resource, method = operation.split(".")
    result = getattr(getattr(client, resource), method)(**kwargs)
    return await result if inspect.isawaitable(result) else result


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def asynchronous(request: pytest.FixtureRequest) -> bool:
    return bool(request.param)


@pytest.fixture
def schema() -> Iterator[dict[str, Any]]:
    path = Path(__file__).parents[1] / "spec" / "openapi" / "pay-current.json"
    yield json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("operation,path,kwargs,payload", CASES, ids=[c[0] for c in CASES])
async def test_read_contracts(
    asynchronous: bool,
    schema: dict[str, Any],
    operation: str,
    path: str,
    kwargs: dict[str, Any],
    payload: Any,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    http_cls = httpx.AsyncClient if asynchronous else httpx.Client
    client_cls = AsyncPayClient if asynchronous else PayClient
    http = http_cls(transport=httpx.MockTransport(handler))
    client = client_cls(api_token="test-token", http_client=http, environment="testnet")
    try:
        result = await invoke(client, operation, kwargs)
        assert len(requests) == 1  # list() fetches one page only
        request = requests[0]
        assert request.method == "GET"
        assert request.url.path == path
        assert request.url.host == "pay.api.testnet.xrocket.exchange"
        assert request.headers["Authorization"] == "Bearer test-token"
        assert "Rocket-Pay-Key" not in request.headers

        aliases = {"invoice_id": "invoiceId", "client_invoice_id": "clientInvoiceId"}
        for key, value in kwargs.items():
            wire_key = aliases.get(key, key)
            if isinstance(value, list):
                assert request.url.params.get_list(wire_key) == value
            else:
                assert request.url.params[wire_key] == str(value)
        assert set(request.url.params.keys()) == {aliases.get(key, key) for key in kwargs}
        documented = {p["name"] for p in schema["paths"][path]["get"].get("parameters", [])}
        assert set(request.url.params.keys()) <= documented
        if operation == "invoices.list":
            assert result.pagination.next == "next+/= cursor"
            invoice = result.items[0]
        elif operation == "invoices.retrieve":
            invoice = result
        else:
            invoice = None
        if invoice is not None:
            assert invoice.price_amount == Decimal("12345678901234567890.123456789")
            assert invoice.status == "a_future_status"
            assert invoice.expires_at is None
            assert invoice.created_at.utcoffset() is not None
            assert invoice.model_extra["futureField"] == {"value": 1}
        if operation == "rates.get":
            assert result[0].rate == Decimal("99999.1234567890123456789")
        if operation == "app.balances":
            assert result.balances[0].balance == Decimal("123.4500")
    finally:
        if asynchronous:
            await client.aclose()
            await http.aclose()
        else:
            client.close()
            http.close()


@pytest.mark.parametrize("identifier", [{"invoice_id": "inv-1"}, {"client_invoice_id": "order-1"}])
async def test_retrieve_accepts_either_identifier(
    asynchronous: bool, identifier: dict[str, str]
) -> None:
    http_cls = httpx.AsyncClient if asynchronous else httpx.Client
    client_cls = AsyncPayClient if asynchronous else PayClient
    http = http_cls(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=INVOICE)))
    client = client_cls(api_token="test", http_client=http)
    try:
        invoice = await invoke(client, "invoices.retrieve", identifier)
        assert invoice.id == "inv-123"
    finally:
        if asynchronous:
            await client.aclose()
            await http.aclose()
        else:
            client.close()
            http.close()


async def test_empty_page_is_terminal_and_omitted_queries_are_absent(asynchronous: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert not request.url.query
        return httpx.Response(200, json={"items": [], "pagination": {"total": 0, "next": None}})

    http_cls = httpx.AsyncClient if asynchronous else httpx.Client
    client_cls = AsyncPayClient if asynchronous else PayClient
    http = http_cls(transport=httpx.MockTransport(handler))
    client = client_cls(api_token="test", http_client=http)
    try:
        page = await invoke(client, "invoices.list", {})
        assert page.items == []
        assert page.pagination.next is None
    finally:
        if asynchronous:
            await client.aclose()
            await http.aclose()
        else:
            client.close()
            http.close()
