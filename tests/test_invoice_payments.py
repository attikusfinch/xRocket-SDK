"""Synthetic invoice-payment contracts, with no live payment records."""

import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from xrocket import AuthenticationError, ResponseValidationError, pay
from xrocket.pay import (
    AsyncPayClient,
    InvoiceBlockchainDetails,
    InvoiceBlockchainTransaction,
    InvoiceInternalTransaction,
    InvoicePayment,
    InvoicePaymentPage,
    InvoicePaymentPagination,
    InvoicePaymentPayer,
    PayClient,
    UnknownInvoiceTransaction,
    models,
)

Client = PayClient | AsyncPayClient
Handler = Callable[[httpx.Request], httpx.Response]
CREATED_AT = "2026-10-17T09:00:00+05:00"
FINALIZED_AT = "2026-10-17T09:01:00+05:00"
EXACT_AMOUNT = "12345678901234567890.000000000100"


def _transaction(kind: str = "internal", **overrides: Any) -> dict[str, Any]:
    return {
        "type": kind,
        "id": f"synthetic-{kind}",
        "status": "pending",
        "createdAt": CREATED_AT,
        **overrides,
    }


def _payment(**overrides: Any) -> dict[str, Any]:
    return {
        "status": "pending",
        "payAmount": EXACT_AMOUNT,
        "payCurrency": "USDT",
        "receiveAmount": "0.000000000100",
        "receiveCurrency": "USDT",
        "transactions": [],
        **overrides,
    }


def _page(items: list[dict[str, Any]], next_cursor: str | None = None) -> dict[str, Any]:
    return {"items": items, "pagination": {"next": next_cursor}}


@pytest.fixture(params=("sync", "async"))
def backend(request: pytest.FixtureRequest) -> str:
    return str(request.param)


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


@asynccontextmanager
async def _sdk(
    backend: str, handler: Handler, *, api_token: str | None = "synthetic-test-token"
) -> AsyncIterator[Client]:
    transport = httpx.MockTransport(handler)
    if backend == "async":
        http: httpx.Client | httpx.AsyncClient = httpx.AsyncClient(transport=transport)
        client: Client = AsyncPayClient(
            api_token=api_token, http_client=http, environment="testnet"
        )
    else:
        http = httpx.Client(transport=transport)
        client = PayClient(api_token=api_token, http_client=http, environment="testnet")
    try:
        yield client
    finally:
        if isinstance(client, AsyncPayClient):
            await client.aclose()
        else:
            client.close()
        if isinstance(http, httpx.AsyncClient):
            await http.aclose()
        else:
            http.close()


@pytest.mark.parametrize(
    "name",
    [
        "InvoicePayment",
        "InvoiceInternalTransaction",
        "InvoiceBlockchainTransaction",
        "InvoicePaymentPayer",
        "InvoiceBlockchainDetails",
        "UnknownInvoiceTransaction",
        "InvoicePaymentPagination",
        "InvoicePaymentPage",
    ],
)
def test_payment_models_share_public_exports(name: str) -> None:
    assert name in pay.__all__
    assert name in models.__all__
    assert getattr(pay, name) is getattr(models, name)


@pytest.mark.parametrize(
    ("identifiers", "wire"),
    [
        ({"invoice_id": "000-invoice"}, {"invoiceId": "000-invoice"}),
        ({"client_invoice_id": "order /+?"}, {"clientInvoiceId": "order /+?"}),
        (
            {"invoice_id": "000-invoice", "client_invoice_id": "client-order"},
            {"invoiceId": "000-invoice", "clientInvoiceId": "client-order"},
        ),
        ({"invoice_id": "i" * 100}, {"invoiceId": "i" * 100}),
        ({"client_invoice_id": "c" * 100}, {"clientInvoiceId": "c" * 100}),
    ],
)
async def test_payment_request_uses_current_route_and_exact_identifier_aliases(
    backend: str, identifiers: dict[str, str], wire: dict[str, str]
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_page([]))

    async with _sdk(backend, respond) as client:
        page = await _resolve(client.invoices.payments(**identifiers))

    assert isinstance(page, InvoicePaymentPage)
    assert len(calls) == 1
    request = calls[0]
    assert request.method == "GET"
    assert request.url.host == "pay.api.testnet.xrocket.exchange"
    assert request.url.path == "/api/v1/invoice/payments"
    assert dict(request.url.params) == wire
    assert request.headers["Authorization"] == "Bearer synthetic-test-token"
    assert request.headers["Accept"] == "application/json"
    assert "Rocket-Pay-Key" not in request.headers


@pytest.mark.parametrize("cursor", ["opaque+/= cursor?&\u2603", ""])
@pytest.mark.parametrize("limit", [1, 1000])
async def test_payment_cursor_is_opaque_and_limit_boundaries_are_preserved(
    backend: str, cursor: str, limit: int
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_page([], "next+/= cursor"))

    async with _sdk(backend, respond) as client:
        page = await _resolve(
            client.invoices.payments(invoice_id="invoice", cursor=cursor, limit=limit)
        )

    assert len(calls) == 1
    assert dict(calls[0].url.params) == {
        "invoiceId": "invoice",
        "cursor": cursor,
        "limit": str(limit),
    }
    assert page.pagination.next == "next+/= cursor"


@pytest.mark.parametrize("next_cursor", [None, "another-opaque-cursor"])
@pytest.mark.parametrize("item_count", [0, 1])
async def test_payment_pagination_is_one_page_and_next_is_independent_of_size(
    backend: str, next_cursor: str | None, item_count: int
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_page([_payment()] * item_count, next_cursor))

    async with _sdk(backend, respond) as client:
        page = await _resolve(client.invoices.payments(invoice_id="invoice", limit=1))

    assert len(calls) == 1
    assert len(page.items) == item_count
    assert isinstance(page.pagination, InvoicePaymentPagination)
    assert page.pagination.next == next_cursor
    assert page.pagination.model_dump() == {"next": next_cursor}


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"invoice_id": ""},
        {"client_invoice_id": ""},
        {"invoice_id": "i" * 101},
        {"client_invoice_id": "c" * 101},
        {"invoice_id": "valid", "client_invoice_id": ""},
        {"invoice_id": "", "client_invoice_id": "valid"},
        {"invoice_id": "valid", "client_invoice_id": "c" * 101},
        *({"invoice_id": "invoice", "limit": value} for value in [0, -1, 1001, True, 1.5, "1"]),
    ],
)
async def test_invalid_payment_arguments_fail_before_the_network(
    backend: str, kwargs: dict[str, Any]
) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid payment arguments reached the network")

    async with _sdk(backend, unexpected_request) as client:
        with pytest.raises(ValueError):
            await _resolve(client.invoices.payments(**kwargs))


async def test_payments_require_sdk_auth_before_the_network(backend: str) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("An unauthenticated invoice payment request reached the network")

    async with _sdk(backend, unexpected_request, api_token=None) as client:
        with pytest.raises(AuthenticationError):
            await _resolve(client.invoices.payments(invoice_id="invoice"))


async def test_payment_response_decodes_each_transaction_and_preserves_future_fields(
    backend: str,
) -> None:
    internal = _transaction(
        status="future_internal_status",
        payAmount=EXACT_AMOUNT,
        payCurrency="USDT",
        receiveAmount="1.2300",
        receiveCurrency="USDT",
        finalizedAt=FINALIZED_AT,
        comment="Synthetic fixture",
        payer={
            "email": "synthetic@example.invalid",
            "telegramId": "000-synthetic-id",
            "telegramUsername": "synthetic_fixture",
            "payerExtra": True,
        },
        transactionExtra=1,
    )
    blockchain = _transaction(
        "blockchain",
        status="future_blockchain_status",
        payAmount=None,
        payCurrency=None,
        receiveAmount=None,
        receiveCurrency=None,
        finalizedAt=None,
        payer={},
        tx={
            "network": "FUTURE_CHAIN",
            "txHash": "synthetic-not-a-real-hash",
            "amount": EXACT_AMOUNT,
            "currency": "USDT",
            "status": "future_chain_status",
            "txExtra": {"confirmations": 2},
        },
    )
    unknown = {"type": "future_transfer", "status": "future_status", "raw": {"value": 7}}
    payload = _page(
        [
            _payment(
                id="000-payment",
                status="future_payment_status",
                finalizedAt=FINALIZED_AT,
                transactions=[internal, blockchain, unknown],
                paymentExtra={"version": 2},
            )
        ]
    )
    payload["pageExtra"] = "retained"
    payload["pagination"]["cursorVersion"] = 2
    async with _sdk(backend, lambda _: httpx.Response(200, json=payload)) as client:
        page = await _resolve(client.invoices.payments(invoice_id="invoice"))

    payment = page.items[0]
    assert isinstance(payment, InvoicePayment)
    assert payment.id == "000-payment"
    assert payment.status == "future_payment_status"
    assert payment.finalized_at.utcoffset() == timedelta(hours=5)
    assert payment.pay_amount == Decimal(EXACT_AMOUNT)
    assert payment.pay_amount.as_tuple().exponent == -12
    assert payment.model_extra == {"paymentExtra": {"version": 2}}
    assert page.model_extra == {"pageExtra": "retained"}
    assert page.pagination.model_extra == {"cursorVersion": 2}

    first, second, third = payment.transactions
    assert isinstance(first, InvoiceInternalTransaction)
    assert first.type == "internal"
    assert first.status == "future_internal_status"
    assert first.created_at.utcoffset() == timedelta(hours=5)
    assert first.finalized_at.utcoffset() == timedelta(hours=5)
    assert first.pay_amount == Decimal(EXACT_AMOUNT)
    assert first.receive_amount.as_tuple().exponent == -4
    assert first.comment == "Synthetic fixture"
    assert isinstance(first.payer, InvoicePaymentPayer)
    assert first.payer.telegram_id == "000-synthetic-id"
    assert first.payer.email == "synthetic@example.invalid"
    assert first.payer.telegram_username == "synthetic_fixture"
    assert first.payer.model_extra == {"payerExtra": True}
    assert first.model_extra == {"transactionExtra": 1}

    assert isinstance(second, InvoiceBlockchainTransaction)
    assert second.type == "blockchain"
    assert second.status == "future_blockchain_status"
    assert second.pay_amount is second.pay_currency is None
    assert second.receive_amount is second.receive_currency is None
    assert second.finalized_at is None
    assert isinstance(second.payer, InvoicePaymentPayer)
    assert second.payer.email is second.payer.telegram_id is second.payer.telegram_username is None
    assert isinstance(second.tx, InvoiceBlockchainDetails)
    assert second.tx.tx_hash == "synthetic-not-a-real-hash"
    assert second.tx.network == "FUTURE_CHAIN"
    assert second.tx.amount == Decimal(EXACT_AMOUNT)
    assert second.tx.status == "future_chain_status"
    assert second.tx.model_extra == {"txExtra": {"confirmations": 2}}

    assert isinstance(third, UnknownInvoiceTransaction)
    assert third.type == "future_transfer"
    assert third.model_dump(by_alias=True) == unknown


@pytest.mark.parametrize("kind", ["internal", "blockchain"])
@pytest.mark.parametrize("explicit_null", [False, True])
def test_pending_payment_accepts_missing_id_and_nullable_transaction_values(
    kind: str, explicit_null: bool
) -> None:
    tx = _transaction(kind)
    overrides: dict[str, Any] = {}
    if explicit_null:
        tx.update(
            dict.fromkeys(
                ["payAmount", "payCurrency", "receiveAmount", "receiveCurrency", "finalizedAt"]
            )
        )
        overrides["finalizedAt"] = None
    payment = InvoicePayment.model_validate(_payment(transactions=[tx], **overrides))
    assert payment.id is None
    assert payment.finalized_at is None
    transaction = payment.transactions[0]
    assert isinstance(transaction, InvoiceInternalTransaction | InvoiceBlockchainTransaction)
    assert transaction.pay_amount is transaction.pay_currency is None
    assert transaction.receive_amount is transaction.receive_currency is None
    assert transaction.finalized_at is None


@pytest.mark.parametrize(
    "field",
    ["status", "payAmount", "payCurrency", "receiveAmount", "receiveCurrency", "transactions"],
)
def test_payment_requires_the_documented_fields(field: str) -> None:
    payload = _payment()
    del payload[field]
    with pytest.raises(ValidationError):
        InvoicePayment.model_validate(payload)


@pytest.mark.parametrize(
    "payload", [{}, {"pagination": {"next": None}}, {"items": []}, {"items": [], "pagination": {}}]
)
def test_payment_page_requires_items_pagination_and_explicit_next(payload: Any) -> None:
    with pytest.raises(ValidationError):
        InvoicePaymentPage.model_validate(payload)


@pytest.mark.parametrize(
    "value", [0.1, True, "NaN", "Infinity", "-Infinity", float("nan"), Decimal("Infinity")]
)
@pytest.mark.parametrize("field", ["payAmount", "receiveAmount"])
@pytest.mark.parametrize("kind", ["payment", "internal", "blockchain"])
def test_payment_and_transaction_money_reject_lossy_or_non_finite_values(
    kind: str, field: str, value: Any
) -> None:
    if kind == "payment":
        payload = _payment(**{field: value})
    else:
        payload = _payment(transactions=[_transaction(kind, **{field: value})])
    with pytest.raises(ValidationError):
        InvoicePayment.model_validate(payload)


@pytest.mark.parametrize("value", [0.1, True, "NaN", "Infinity", "-Infinity"])
def test_blockchain_details_money_rejects_lossy_or_non_finite_values(value: Any) -> None:
    with pytest.raises(ValidationError):
        InvoiceBlockchainDetails.model_validate(
            {
                "network": "TON",
                "txHash": "synthetic",
                "amount": value,
                "currency": "USDT",
                "status": "pending",
            }
        )


@pytest.mark.parametrize("kind", ["internal", "blockchain"])
@pytest.mark.parametrize("field", ["createdAt", "finalizedAt"])
def test_transaction_timestamps_require_timezone(kind: str, field: str) -> None:
    payload = _payment(transactions=[_transaction(kind, **{field: "2026-10-17T09:00:00"})])
    with pytest.raises(ValidationError):
        InvoicePayment.model_validate(payload)


def test_payment_finalized_timestamp_requires_timezone() -> None:
    with pytest.raises(ValidationError):
        InvoicePayment.model_validate(_payment(finalizedAt="2026-10-17T09:00:00"))


@pytest.mark.parametrize(
    "transaction",
    [
        {"type": "internal", "status": "pending", "createdAt": CREATED_AT},
        {"type": "blockchain", "id": "synthetic", "status": "pending"},
        _transaction(payAmount=0.1),
        _transaction("blockchain", tx={"network": "TON"}),
        {"id": "synthetic", "status": "pending", "createdAt": CREATED_AT},
        {"type": 7, "raw": "untyped"},
        {"type": None, "raw": "untyped"},
    ],
)
async def test_malformed_known_or_untyped_transactions_fail_response_validation(
    backend: str, transaction: dict[str, Any]
) -> None:
    payload = _page([_payment(transactions=[deepcopy(transaction)])])
    async with _sdk(backend, lambda _: httpx.Response(200, json=payload)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.invoices.payments(invoice_id="invoice"))


@pytest.mark.parametrize("kind", ["internal", "blockchain"])
@pytest.mark.parametrize("field", ["id", "status", "createdAt"])
def test_known_transactions_do_not_fallback_when_required_fields_are_missing(
    kind: str, field: str
) -> None:
    transaction = _transaction(kind)
    del transaction[field]
    with pytest.raises(ValidationError):
        InvoicePayment.model_validate(_payment(transactions=[transaction]))


@pytest.mark.parametrize("field", ["network", "txHash", "amount", "currency", "status"])
def test_present_blockchain_details_require_each_documented_field(field: str) -> None:
    details = {
        "network": "TON",
        "txHash": "synthetic",
        "amount": "1.0000",
        "currency": "USDT",
        "status": "pending",
    }
    del details[field]
    with pytest.raises(ValidationError):
        InvoicePayment.model_validate(
            _payment(transactions=[_transaction("blockchain", tx=details)])
        )
