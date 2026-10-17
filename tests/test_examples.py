"""Execute the shipped examples with synthetic inputs and no network side effects."""

import hashlib
import hmac
import inspect
import json
import runpy
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from xrocket import RequestTimeoutError
from xrocket.pay import InvoiceWebhook, UnknownWebhook, WebhookPayloadError, WebhookSignatureError

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
TOKEN = "synthetic-example-testnet-token"
SECRET = "synthetic-example-webhook-secret"
STABLE_ID = "synthetic-application-persisted-invoice-id"
INVOICE = {
    "id": "synthetic-example-invoice",
    "priceCurrency": "USDT",
    "priceAmount": "1.2500",
    "createdAt": "2026-10-18T00:00:00Z",
    "status": "a_future_invoice_status",
    "links": {"telegramBotLink": "https://example.invalid/invoice"},
}


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XROCKET_PAY_TESTNET_TOKEN", TOKEN)
    monkeypatch.setenv("XROCKET_PAY_TESTNET_CLIENT_INVOICE_ID", STABLE_ID)
    monkeypatch.setenv("XROCKET_PAY_TESTNET_WEBHOOK_SECRET", SECRET)

    def reject_network(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Examples must use MockTransport in offline tests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_network)


def test_examples_import_without_credentials_or_io(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "XROCKET_PAY_TESTNET_TOKEN",
        "XROCKET_PAY_TESTNET_CLIENT_INVOICE_ID",
        "XROCKET_PAY_TESTNET_WEBHOOK_SECRET",
    ):
        monkeypatch.delenv(name)
    for example in ("read", "write", "webhook"):
        runpy.run_path(str(EXAMPLES / f"pay_{example}.py"))


async def _invoke(example: str, operation: str, asynchronous: bool, http: Any) -> Any:
    namespace = runpy.run_path(str(EXAMPLES / f"pay_{example}.py"))
    function = namespace[f"{operation}_{'async' if asynchronous else 'sync'}"]
    result = function(http_client=http)
    return await result if inspect.isawaitable(result) else result


async def _close(http: Any, asynchronous: bool) -> None:
    if asynchronous:
        await http.aclose()
    else:
        http.close()


def _assert_testnet(request: httpx.Request) -> None:
    assert request.url.scheme == "https"
    assert request.url.host == "pay.api.testnet.xrocket.exchange"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
async def test_read_example_executes_one_explicit_page_and_retains_http_ownership(
    asynchronous: bool,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        _assert_testnet(request)
        assert request.method == "GET"
        assert not request.content
        if request.url.path == "/api/v1/balances":
            assert not request.url.query
            return httpx.Response(
                200,
                json={
                    "balances": [
                        {"asset": "USDT", "balance": "1.2500", "available": "1.2500", "holds": "0"}
                    ]
                },
            )
        assert request.url.path == "/api/v1/invoices"
        assert list(request.url.params.multi_items()) == [("limit", "100")]
        return httpx.Response(
            200,
            json={
                "items": [INVOICE],
                "pagination": {"next": "opaque+/= next", "total": 2},
            },
        )

    cls = httpx.AsyncClient if asynchronous else httpx.Client
    http = cls(transport=httpx.MockTransport(handler))
    try:
        balances, page = await _invoke("read", "read", asynchronous, http)
        assert balances.balances[0].balance == Decimal("1.2500")
        assert page.items[0].status == "a_future_invoice_status"
        assert page.pagination.next == "opaque+/= next"
        assert len(requests) == 2  # A nonempty cursor must not trigger a second page.
        assert not http.is_closed
    finally:
        await _close(http, asynchronous)


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
async def test_write_example_sends_exact_money_and_application_stable_id_once(
    asynchronous: bool,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        _assert_testnet(request)
        assert request.method == "POST"
        assert request.url.path == "/api/v1/invoices"
        assert not request.url.query
        assert json.loads(request.content) == {
            "priceCurrency": "USDT",
            "priceAmount": "1.2500",
            "clientInvoiceId": STABLE_ID,
            "expiresIn": 300_000,
        }
        assert b'"priceAmount":"1.2500"' in request.content
        return httpx.Response(200, json={**INVOICE, "clientInvoiceId": STABLE_ID})

    cls = httpx.AsyncClient if asynchronous else httpx.Client
    http = cls(transport=httpx.MockTransport(handler))
    try:
        invoice = await _invoke("write", "create_invoice", asynchronous, http)
        assert invoice.price_amount == Decimal("1.2500")
        assert invoice.client_invoice_id == STABLE_ID
        assert invoice.status == "a_future_invoice_status"
        assert len(requests) == 1
        assert not http.is_closed
    finally:
        await _close(http, asynchronous)


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
async def test_write_example_propagates_timeout_without_retry_or_lookup(asynchronous: bool) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    cls = httpx.AsyncClient if asynchronous else httpx.Client
    http = cls(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RequestTimeoutError):
            await _invoke("write", "create_invoice", asynchronous, http)
        assert len(requests) == 1
        assert requests[0].method == "POST"
        assert not http.is_closed
    finally:
        await _close(http, asynchronous)


def _signed_headers(body: bytes) -> dict[str, str]:
    timestamp = str(time.time_ns() // 1_000_000)
    return {
        "Signature-Timestamp": timestamp,
        "Signature-Version": "v1",
        "Signature": hmac.new(
            SECRET.encode(),
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest(),
    }


def test_webhook_example_distinguishes_finality_and_future_deliveries() -> None:
    namespace = runpy.run_path(str(EXAMPLES / "pay_webhook.py"))
    decode = namespace["decode_delivery"]
    finality = namespace["payment_finality"]
    envelope = {
        "id": "synthetic-delivery-id",
        "timestamp": "2026-10-18T00:00:00Z",
        "type": "invoice",
    }
    for status, finalized_at, expected in [
        ("pending", None, False),
        ("completed", "2026-10-18T00:00:00Z", True),
        ("a_future_payment_status", None, False),
    ]:
        payload = {
            **envelope,
            "data": {
                "event": "payment_status_changed",
                "invoice": INVOICE,
                "payment": {
                    "id": "synthetic-payment-id",
                    "status": status,
                    "payAmount": "1.2500",
                    "payCurrency": "USDT",
                    "receiveAmount": "1.2500",
                    "receiveCurrency": "USDT",
                    "transactions": [],
                    "finalizedAt": finalized_at,
                },
            },
        }
        body = json.dumps(payload).encode()
        delivery = decode(body, _signed_headers(body))
        assert isinstance(delivery, InvoiceWebhook)
        assert delivery.id == "synthetic-delivery-id"
        assert delivery.data.payment.id == "synthetic-payment-id"
        assert delivery.data.payment.status == status
        assert finality(delivery) is expected  # Finality alone does not classify success.
        assert delivery.raw_body == body

    for data in [
        {"event": "invoice_status_changed", "invoice": INVOICE},
        {"event": "future_invoice_event", "status": "paid", "finalizedAt": "anything"},
    ]:
        body = json.dumps({**envelope, "data": data}).encode()
        delivery = decode(body, _signed_headers(body))
        assert finality(delivery) is None
        if data["event"] == "future_invoice_event":
            assert isinstance(delivery, UnknownWebhook)
            assert delivery.raw_payload["data"] == data


def test_webhook_example_authenticates_before_parsing_json() -> None:
    decode = runpy.run_path(str(EXAMPLES / "pay_webhook.py"))["decode_delivery"]
    malformed_body = b"{not JSON"
    headers = _signed_headers(malformed_body)
    invalid_headers = {**headers, "Signature": "0" * 64}
    with pytest.raises(WebhookSignatureError):
        decode(malformed_body, invalid_headers)
    with pytest.raises(WebhookPayloadError):
        decode(malformed_body, headers)
