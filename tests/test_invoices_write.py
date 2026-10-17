"""Offline contracts for Current Pay invoice creation and deletion."""

import inspect
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

import xrocket.pay as pay
import xrocket.pay.models as models
from xrocket import (
    APIError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ResponseValidationError,
    ServerError,
)
from xrocket._core.serialization import RequestModel, serialize_request
from xrocket.pay import (
    AsyncPayClient,
    Invoice,
    InvoiceCallback,
    InvoiceCallbackRequest,
    InvoiceCreateRequest,
    InvoiceCustomerRequest,
    InvoiceURLRequest,
    PayClient,
)
from xrocket.pay.resources.invoices import AsyncInvoicesResource, InvoicesResource

INVOICE = {
    "id": "synthetic-invoice",
    "priceCurrency": "USDT",
    "priceAmount": "12345678901234567890.12345678900000000001",
    "createdAt": "2026-10-17T08:00:00+05:00",
    "status": "a_future_invoice_status",
    "links": {
        "telegramBotLink": "https://example.invalid/invoice",
        "futureLink": "preserved",
    },
    "futureResponseField": {"value": 1},
}
Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def asynchronous(request: pytest.FixtureRequest) -> bool:
    return bool(request.param)


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


@asynccontextmanager
async def _client(
    asynchronous: bool,
    handler: Handler,
    *,
    token: str | None = "synthetic-invoice-token",
    **http_options: Any,
) -> AsyncIterator[Any]:
    http_cls = httpx.AsyncClient if asynchronous else httpx.Client
    client_cls = AsyncPayClient if asynchronous else PayClient
    http = http_cls(transport=httpx.MockTransport(handler), **http_options)
    client = client_cls(api_token=token, http_client=http, environment="testnet")
    try:
        yield client
    finally:
        if asynchronous:
            await client.aclose()
            assert not http.is_closed
            await http.aclose()
        else:
            client.close()
            assert not http.is_closed
            http.close()


async def _write(client: Any, operation: str) -> Any:
    if operation == "create":
        return await _resolve(
            client.invoices.create(request=InvoiceCreateRequest(price_currency="USDT"))
        )
    return await _resolve(client.invoices.delete(invoice_id="synthetic-invoice"))


async def test_create_sends_every_documented_field_and_returns_typed_invoice(
    asynchronous: bool,
) -> None:
    calls: list[httpx.Request] = []
    amount = Decimal("12345678901234567890.12345678900000000001")
    body = InvoiceCreateRequest(
        price_currency="USDT",
        price_amount=amount,
        num_payments=1_000_000,
        payout_currency="TON",
        pay_currencies=["USDT", "TON"],
        client_invoice_id="client +/= &?%#ю",
        description="Заказ 🎁",
        expires_in=1_800_000,
        callback=InvoiceCallbackRequest(
            callback_url="https://example.invalid/callback",
            payload={"custom": ["ю", None, True, Decimal("0.0000000000000000001")]},
        ),
        url=InvoiceURLRequest(
            success_url="https://example.invalid/success",
            cancel_url="https://example.invalid/cancel",
        ),
        customer=InvoiceCustomerRequest(
            id="synthetic-customer",
            email="synthetic@example.invalid",
            telegram_id="000123",
            telegram_username="synthetic_username",
        ),
        data={"custom": {"enabled": False}, "zero": 0},
        platform_id="synthetic-platform",
    )
    original_fields = body.model_fields_set.copy()

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=INVOICE)

    async with _client(asynchronous, respond) as client:
        result = await _resolve(client.invoices.create(request=body))

    assert len(calls) == 1
    request = calls[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/invoices"
    assert request.url.host == "pay.api.testnet.xrocket.exchange"
    assert not request.url.query
    assert request.headers["authorization"] == "Bearer synthetic-invoice-token"
    assert request.headers["content-type"] == "application/json"
    assert "idempotency-key" not in request.headers
    assert "Rocket-Pay-Key" not in request.headers
    assert json.loads(request.content) == {
        "priceCurrency": "USDT",
        "priceAmount": str(amount),
        "numPayments": 1_000_000,
        "payoutCurrency": "TON",
        "payCurrencies": ["USDT", "TON"],
        "clientInvoiceId": "client +/= &?%#ю",
        "description": "Заказ 🎁",
        "expiresIn": 1_800_000,
        "callback": {
            "callbackUrl": "https://example.invalid/callback",
            "payload": {"custom": ["ю", None, True, "1E-19"]},
        },
        "url": {
            "successUrl": "https://example.invalid/success",
            "cancelUrl": "https://example.invalid/cancel",
        },
        "customer": {
            "id": "synthetic-customer",
            "email": "synthetic@example.invalid",
            "telegramId": "000123",
            "telegramUsername": "synthetic_username",
        },
        "data": {"custom": {"enabled": False}, "zero": 0},
        "platformId": "synthetic-platform",
    }
    assert body.model_fields_set == original_fields
    assert body.price_amount.as_tuple() == amount.as_tuple()
    assert isinstance(result, Invoice)
    assert result.price_amount.as_tuple() == amount.as_tuple()
    assert result.created_at.utcoffset() is not None
    assert result.status == "a_future_invoice_status"
    assert result.model_extra == {"futureResponseField": {"value": 1}}
    assert result.links.model_extra == {"futureLink": "preserved"}


@pytest.mark.parametrize(
    "body,expected",
    [
        pytest.param(
            {"price_currency": "USDT"}, {"priceCurrency": "USDT"}, id="neither-amount"
        ),
        pytest.param(
            {"price_currency": "USD", "min_payment": "0.00000000000000000001"},
            {"priceCurrency": "USD", "minPayment": "1E-20"},
            id="open-minimum",
        ),
        pytest.param(
            {"price_currency": "USDT", "price_amount": Decimal("-0.0000"), "expires_in": 0},
            {"priceCurrency": "USDT", "priceAmount": "-0.0000", "expiresIn": 0},
            id="explicit-zero-and-milliseconds",
        ),
        pytest.param(
            {
                "price_currency": "",
                "payout_currency": "",
                "pay_currencies": [],
                "client_invoice_id": "",
                "description": "",
                "expires_in": 0,
                "callback": {"callbackUrl": "", "payload": {}},
                "url": {"successUrl": "", "cancelUrl": ""},
                "customer": {},
                "data": {},
                "platform_id": "",
            },
            {
                "priceCurrency": "",
                "payoutCurrency": "",
                "payCurrencies": [],
                "clientInvoiceId": "",
                "description": "",
                "expiresIn": 0,
                "callback": {"callbackUrl": "", "payload": {}},
                "url": {"successUrl": "", "cancelUrl": ""},
                "customer": {},
                "data": {},
                "platformId": "",
            },
            id="explicit-empty-values",
        ),
        pytest.param(
            {"price_currency": "USDT", "callback": {}, "url": {}, "customer": {}},
            {"priceCurrency": "USDT", "callback": {}, "url": {}, "customer": {}},
            id="empty-nested-objects",
        ),
    ],
)
async def test_create_omission_and_explicit_values_keep_wire_semantics(
    asynchronous: bool, body: dict[str, Any], expected: dict[str, Any]
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=INVOICE)

    async with _client(asynchronous, respond) as client:
        result = await _resolve(
            client.invoices.create(request=InvoiceCreateRequest.model_validate(body))
        )

    assert isinstance(result, Invoice)
    assert len(calls) == 1
    assert json.loads(calls[0].content) == expected


@pytest.mark.parametrize("field", ["price_amount", "min_payment"])
@pytest.mark.parametrize(
    "amount",
    [
        "123456789012345678901234567890.00000000000000000001",
        Decimal("999999999999999999999999999999.12345000000000000000"),
        Decimal("-0.0000"),
        "1E-40",
        Decimal("-0.0001"),
    ],
)
def test_create_amounts_are_exact_finite_decimal_strings(
    field: str, amount: str | Decimal
) -> None:
    body = InvoiceCreateRequest.model_validate({"priceCurrency": "USDT", field: amount})
    alias = "priceAmount" if field == "price_amount" else "minPayment"
    assert getattr(body, field).as_tuple() == Decimal(amount).as_tuple()
    assert json.loads(serialize_request(body)) == {
        "priceCurrency": "USDT",
        alias: str(Decimal(amount)),
    }


@pytest.mark.parametrize("field", ["price_amount", "min_payment"])
@pytest.mark.parametrize(
    "amount",
    [0, 1, 0.1, True, False, None, b"1", "", "invalid", "NaN", "Infinity", Decimal("NaN")],
)
def test_create_amounts_reject_implicit_coercion_and_non_finite_values(
    field: str, amount: Any
) -> None:
    with pytest.raises(ValidationError):
        InvoiceCreateRequest.model_validate({"price_currency": "USDT", field: amount})


@pytest.mark.parametrize(
    "amounts",
    [
        {"price_amount": "1", "min_payment": "1"},
        {"priceAmount": "0", "minPayment": "0"},
        {"price_amount": Decimal("-0"), "min_payment": Decimal("0")},
    ],
)
def test_create_rejects_both_amounts_even_when_zero(amounts: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        InvoiceCreateRequest.model_validate({"price_currency": "USDT", **amounts})


@pytest.mark.parametrize(
    "field",
    [
        "price_amount",
        "min_payment",
        "num_payments",
        "payout_currency",
        "pay_currencies",
        "client_invoice_id",
        "description",
        "expires_in",
        "callback",
        "url",
        "customer",
        "data",
        "platform_id",
    ],
)
def test_optional_create_fields_can_be_omitted_but_cannot_be_explicit_null(field: str) -> None:
    assert json.loads(serialize_request(InvoiceCreateRequest(price_currency="USDT"))) == {
        "priceCurrency": "USDT"
    }
    with pytest.raises(ValidationError):
        InvoiceCreateRequest.model_validate({"price_currency": "USDT", field: None})


@pytest.mark.parametrize(
    "model,field",
    [
        (InvoiceCallbackRequest, "callback_url"),
        (InvoiceCallbackRequest, "payload"),
        (InvoiceURLRequest, "success_url"),
        (InvoiceURLRequest, "cancel_url"),
        (InvoiceCustomerRequest, "id"),
        (InvoiceCustomerRequest, "email"),
        (InvoiceCustomerRequest, "telegram_id"),
        (InvoiceCustomerRequest, "telegram_username"),
    ],
)
def test_optional_nested_fields_reject_explicit_null(model: Any, field: str) -> None:
    assert json.loads(serialize_request(model())) == {}
    with pytest.raises(ValidationError):
        model.model_validate({field: None})


@pytest.mark.parametrize("value", [1, 1_000_000])
def test_num_payments_accepts_documented_integer_boundaries(value: int) -> None:
    body = InvoiceCreateRequest(price_currency="USDT", num_payments=value)
    assert json.loads(serialize_request(body))["numPayments"] == value


@pytest.mark.parametrize("value", [0, -1, 1_000_001, 1.0, 1.5, "1", True, False])
def test_num_payments_rejects_bounds_and_non_integer_inputs(value: Any) -> None:
    with pytest.raises(ValidationError):
        InvoiceCreateRequest(price_currency="USDT", num_payments=value)


@pytest.mark.parametrize("value", [-1, 0, 1, 1_800_000, 2**80])
def test_expires_in_is_an_integer_in_milliseconds_without_invented_range(value: int) -> None:
    body = InvoiceCreateRequest(price_currency="USDT", expires_in=value)
    assert json.loads(serialize_request(body))["expiresIn"] == value


@pytest.mark.parametrize("value", [0.0, 1.1, "1800000", True, False])
def test_expires_in_rejects_coercion(value: Any) -> None:
    with pytest.raises(ValidationError):
        InvoiceCreateRequest(price_currency="USDT", expires_in=value)


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"price_currency": None},
        {"price_currency": 1},
        {"payout_currency": 1},
        {"client_invoice_id": 1},
        {"description": 1},
        {"platform_id": 1},
        {"pay_currencies": "USDT"},
        {"pay_currencies": ("USDT",)},
        {"pay_currencies": [1]},
        {"callback": []},
        {"customer": []},
        {"url": []},
        {"data": []},
        {"callback": {"payload": []}},
        {"customer": {"telegramId": 123}},
    ],
)
def test_create_requires_the_documented_field_types(changes: dict[str, Any]) -> None:
    payload = {"price_currency": "USDT", **changes} if changes else {}
    with pytest.raises(ValidationError):
        InvoiceCreateRequest.model_validate(payload)


@pytest.mark.parametrize(
    "model,field,maximum",
    [
        (InvoiceCreateRequest, "description", 1000),
        (InvoiceCallbackRequest, "callback_url", 500),
        (InvoiceURLRequest, "success_url", 500),
        (InvoiceURLRequest, "cancel_url", 500),
    ],
)
def test_request_strings_enforce_only_the_documented_max_lengths(
    model: Any, field: str, maximum: int
) -> None:
    required = {"price_currency": "USDT"} if model is InvoiceCreateRequest else {}
    body = model.model_validate({**required, field: "ю" * maximum})
    assert getattr(body, field) == "ю" * maximum
    with pytest.raises(ValidationError):
        model.model_validate({**required, field: "ю" * (maximum + 1)})


def test_create_does_not_guess_formats_create_id_bounds_or_json_size_units() -> None:
    body = InvoiceCreateRequest(
        price_currency="unknown future currency",
        client_invoice_id="x" * 101,
        callback=InvoiceCallbackRequest(callback_url="not a URL", payload={"large": "я" * 5000}),
        url=InvoiceURLRequest(success_url="relative/path", cancel_url="a custom scheme"),
        customer=InvoiceCustomerRequest(
            id="", email="not an email", telegram_id="unknown", telegram_username="@name"
        ),
        data={"large": "я" * 5000},
        platform_id="not-a-uuid",
    )
    wire = json.loads(serialize_request(body))
    assert wire["clientInvoiceId"] == "x" * 101
    assert wire["callback"]["payload"] == {"large": "я" * 5000}
    assert wire["customer"]["email"] == "not an email"
    assert wire["platformId"] == "not-a-uuid"


@pytest.mark.parametrize(
    "model",
    [InvoiceCreateRequest, InvoiceCallbackRequest, InvoiceURLRequest, InvoiceCustomerRequest],
)
def test_request_models_reject_unknown_fields_instead_of_forwarding_response_extras(
    model: Any,
) -> None:
    required = {"price_currency": "USDT"} if model is InvoiceCreateRequest else {}
    with pytest.raises(ValidationError):
        model.model_validate({**required, "futureResponseField": True})


@pytest.mark.parametrize(
    "factory",
    [
        lambda: {"priceCurrency": "USDT"},
        lambda: Invoice.model_validate(INVOICE),
        lambda: InvoiceURLRequest(),
        lambda: None,
    ],
)
async def test_create_rejects_non_invoice_request_bodies_before_io(
    asynchronous: bool, factory: Callable[[], Any]
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=INVOICE)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(TypeError):
            await _resolve(client.invoices.create(request=factory()))
    assert calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("price_amount", 0.1),
        ("min_payment", 1),
        ("num_payments", True),
        ("expires_in", "1800000"),
        ("description", "x" * 1001),
        ("pay_currencies", [1]),
        ("platform_id", None),
    ],
)
@pytest.mark.parametrize("constructed", [False, True], ids=["mutated", "constructed"])
async def test_create_revalidates_bypassed_request_values_before_io(
    asynchronous: bool, field: str, value: Any, constructed: bool
) -> None:
    calls: list[httpx.Request] = []
    if constructed:
        body = InvoiceCreateRequest.model_construct(price_currency="USDT", **{field: value})
    else:
        body = InvoiceCreateRequest(price_currency="USDT")
        setattr(body, field, value)

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=INVOICE)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.invoices.create(request=body))
    assert calls == []


async def test_constructed_unset_required_currency_is_sent_without_mutating_source_fields_set(
    asynchronous: bool,
) -> None:
    calls: list[httpx.Request] = []
    body = InvoiceCreateRequest.model_construct(_fields_set=set(), price_currency="USDT")

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=INVOICE)

    async with _client(asynchronous, respond) as client:
        result = await _resolve(client.invoices.create(request=body))
    assert isinstance(result, Invoice)
    assert len(calls) == 1
    assert json.loads(calls[0].content) == {"priceCurrency": "USDT"}
    assert body.model_fields_set == set()


async def test_create_revalidates_amount_conflict_added_by_mutation(asynchronous: bool) -> None:
    calls: list[httpx.Request] = []
    body = InvoiceCreateRequest(price_currency="USDT", price_amount="0")
    body.min_payment = Decimal("0")

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=INVOICE)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.invoices.create(request=body))
    assert calls == []


@pytest.mark.parametrize("location", ["data", "callback_payload", "callback_field"])
async def test_response_models_cannot_be_forwarded_in_nested_invoice_requests(
    asynchronous: bool, location: str
) -> None:
    calls: list[httpx.Request] = []
    response = InvoiceCallback.model_validate({"callbackUrl": "synthetic", "future": True})
    body = InvoiceCreateRequest(price_currency="USDT")
    if location == "data":
        body.data = {"nested": [response]}
    elif location == "callback_payload":
        body.callback = InvoiceCallbackRequest(payload={"nested": response})
    else:
        body.callback = response

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=INVOICE)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(TypeError):
            await _resolve(client.invoices.create(request=body))
    assert calls == []


@pytest.mark.parametrize(
    "ids",
    [
        {"invoice_id": "0"},
        {"client_invoice_id": "0"},
        {"invoice_id": "x" * 100},
        {"client_invoice_id": "x" * 100},
        {"invoice_id": " inv +/= &?%#ю ", "client_invoice_id": " client +/= &?%#ю "},
    ],
)
async def test_delete_uses_singular_path_literal_identifiers_and_bodyless_200(
    asynchronous: bool, ids: dict[str, str]
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    async with _client(asynchronous, respond) as client:
        result = await _resolve(client.invoices.delete(**ids))

    assert result is None
    assert len(calls) == 1
    request = calls[0]
    assert request.method == "DELETE"
    assert request.url.path == "/api/v1/invoice"
    assert request.url.host == "pay.api.testnet.xrocket.exchange"
    assert request.headers["authorization"] == "Bearer synthetic-invoice-token"
    assert request.content == b""
    assert "content-type" not in request.headers
    assert "idempotency-key" not in request.headers
    aliases = {"invoice_id": "invoiceId", "client_invoice_id": "clientInvoiceId"}
    assert request.url.params.multi_items() == [(aliases[key], value) for key, value in ids.items()]


@pytest.mark.parametrize(
    "ids",
    [
        {},
        {"invoice_id": None, "client_invoice_id": None},
        {"invoice_id": ""},
        {"client_invoice_id": ""},
        {"invoice_id": "valid", "client_invoice_id": ""},
        {"invoice_id": "x" * 101},
        {"client_invoice_id": "x" * 101},
        {"invoice_id": 0},
        {"invoice_id": 123},
        {"client_invoice_id": False},
        {"client_invoice_id": []},
        {"invoice_id": b"id", "client_invoice_id": "valid"},
    ],
)
async def test_delete_rejects_missing_empty_oversized_and_non_string_ids_before_io(
    asynchronous: bool, ids: dict[str, Any]
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(ValueError):
            await _resolve(client.invoices.delete(**ids))
    assert calls == []


@pytest.mark.parametrize("operation", ["create", "delete"])
async def test_invoice_writes_require_sdk_auth_before_io(
    asynchronous: bool, operation: str
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    async with _client(
        asynchronous,
        respond,
        token=None,
        headers={"authorization": "Bearer unrelated-default"},
        auth=("unrelated-user", "unrelated-password"),
    ) as client:
        with pytest.raises(AuthenticationError):
            await _write(client, operation)
    assert calls == []


@pytest.mark.parametrize("operation", ["create", "delete"])
@pytest.mark.parametrize("status", [201, 202, 204])
async def test_invoice_writes_require_exact_documented_200(
    asynchronous: bool, operation: str, status: int
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if operation == "create":
            return httpx.Response(status, json=INVOICE)
        return httpx.Response(status)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(ResponseValidationError):
            await _write(client, operation)
    assert len(calls) == 1


@pytest.mark.parametrize("content", [b"", b"null", b"{}", b"[]", b"not json"])
async def test_create_rejects_invalid_invoice_success_response(
    asynchronous: bool, content: bytes
) -> None:
    async with _client(
        asynchronous, lambda _: httpx.Response(200, content=content)
    ) as client:
        with pytest.raises(ResponseValidationError):
            await _write(client, "create")


@pytest.mark.parametrize("content", [b" ", b"null", b"{}", b"[]", b"true"])
async def test_delete_does_not_treat_json_or_whitespace_as_bodyless_success(
    asynchronous: bool, content: bytes
) -> None:
    async with _client(
        asynchronous, lambda _: httpx.Response(200, content=content)
    ) as client:
        with pytest.raises(ResponseValidationError):
            await _write(client, "delete")


@pytest.mark.parametrize("operation", ["create", "delete"])
@pytest.mark.parametrize(
    "status,error",
    [(400, APIError), (401, AuthenticationError), (404, NotFoundError),
     (429, RateLimitError), (500, ServerError)],
)
async def test_invoice_write_errors_preserve_problem_metadata_and_do_not_retry(
    asynchronous: bool, operation: str, status: int, error: type[APIError]
) -> None:
    calls: list[httpx.Request] = []
    problem = {
        "type": "/api/problems/synthetic_invoice_problem",
        "status": status,
        "detail": "Synthetic problem",
        "future": {"preserved": True},
    }

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            json=problem,
            headers={"x-request-id": "synthetic-write-request", "retry-after": "9"},
        )

    async with _client(asynchronous, respond) as client:
        with pytest.raises(error) as caught:
            await _write(client, operation)
    assert len(calls) == 1
    assert caught.value.status_code == status
    assert caught.value.problem == problem
    assert caught.value.request_id == "synthetic-write-request"
    assert caught.value.retry_after == "9"


@pytest.mark.parametrize("operation", ["create", "delete"])
async def test_invoice_mutations_do_not_follow_redirects(
    asynchronous: bool, operation: str
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(307, headers={"location": "https://other.invalid/sink"})

    async with _client(asynchronous, respond, follow_redirects=True) as client:
        with pytest.raises(APIError) as caught:
            await _write(client, operation)
    assert caught.value.status_code == 307
    assert len(calls) == 1


def test_public_request_exports_and_sync_async_signatures_stay_symmetric() -> None:
    for name in (
        "InvoiceCreateRequest",
        "InvoiceCallbackRequest",
        "InvoiceURLRequest",
        "InvoiceCustomerRequest",
    ):
        assert getattr(pay, name) is getattr(models, name)
        assert name in pay.__all__
        assert name in models.__all__
        assert issubclass(getattr(pay, name), RequestModel)
    assert not issubclass(Invoice, RequestModel)
    assert not issubclass(InvoiceCallback, RequestModel)
    for method in ("create", "delete"):
        sync = inspect.signature(getattr(InvoicesResource, method))
        asynchronous = inspect.signature(getattr(AsyncInvoicesResource, method))
        assert sync == asynchronous
        assert all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            for name, parameter in sync.parameters.items()
            if name != "self"
        )
    assert set(inspect.signature(InvoicesResource.create).parameters) == {"self", "request"}
    assert set(inspect.signature(InvoicesResource.delete).parameters) == {
        "self", "invoice_id", "client_invoice_id"
    }


def test_request_field_aliases_and_operation_policies_match_the_saved_snapshot() -> None:
    snapshot = json.loads(
        (Path(__file__).parents[1] / "spec" / "openapi" / "pay-current.json").read_text(
            encoding="utf-8"
        )
    )
    schemas = snapshot["components"]["schemas"]
    for model, schema_name in (
        (InvoiceCreateRequest, "InvoiceCreateRequestDto"),
        (InvoiceCallbackRequest, "InvoiceCallbackRequestDto"),
        (InvoiceURLRequest, "InvoiceUrlRequestDto"),
        (InvoiceCustomerRequest, "InvoiceCustomerRequestDto"),
    ):
        assert {field.alias for field in model.model_fields.values()} == set(
            schemas[schema_name]["properties"]
        )
    assert schemas["InvoiceCreateRequestDto"]["required"] == ["priceCurrency"]
    create = snapshot["paths"]["/api/v1/invoices"]["post"]
    delete = snapshot["paths"]["/api/v1/invoice"]["delete"]
    assert set(create["responses"]) & {"200", "201", "204"} == {"200"}
    assert set(delete["responses"]) & {"200", "201", "204"} == {"200"}
    assert "content" not in delete["responses"]["200"]
    assert "requestBody" not in delete
