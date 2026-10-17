"""Offline contracts for creating Current Pay invoice payment addresses."""

import inspect
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
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
    PermissionDeniedError,
    RateLimitError,
    RequestTimeoutError,
    ResponseValidationError,
    ServerError,
)
from xrocket._core.serialization import RequestModel, serialize_request
from xrocket.pay import (
    AsyncPayClient,
    InvoiceCreatePaymentAddressRequest,
    InvoiceCreateRequest,
    InvoicePaymentAddress,
    PayClient,
)
from xrocket.pay.resources.invoices import AsyncInvoicesResource, InvoicesResource

ADDRESS = {
    "address": "synthetic-deposit-address",
    "payCurrency": "USDT",
    "payNetwork": "future_network",
    "expiresAt": "2026-10-17T08:00:00.123456+05:30",
    "minAmount": "12345678901234567890.12345678900000000001",
    "futureResponseField": {"preserved": True},
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
    token: str | None = "synthetic-address-token",
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


async def _create(client: Any) -> Any:
    return await _resolve(
        client.invoices.create_payment_address(
            request=InvoiceCreatePaymentAddressRequest(pay_network="TON"),
            invoice_id="synthetic-invoice",
        )
    )


@pytest.mark.parametrize("network", ["TON", "BSC", "ETH", "BTC", "TRX", "SOL"])
async def test_create_sends_query_ids_and_network_body_and_decodes_exact_201(
    asynchronous: bool, network: str
) -> None:
    calls: list[httpx.Request] = []
    body = InvoiceCreatePaymentAddressRequest.model_validate({"payNetwork": network})
    original_fields = body.model_fields_set.copy()
    invoice_id = " inv +/= &?%#ю "
    client_invoice_id = " client +/= &?%#ю "

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json=ADDRESS)

    async with _client(asynchronous, respond) as client:
        result = await _resolve(
            client.invoices.create_payment_address(
                request=body, invoice_id=invoice_id, client_invoice_id=client_invoice_id
            )
        )

    assert len(calls) == 1
    request = calls[0]
    assert request.method == "POST"
    assert request.url.host == "pay.api.testnet.xrocket.exchange"
    assert request.url.path == "/api/v1/invoices/payments/address"
    assert request.url.params.multi_items() == [
        ("invoiceId", invoice_id), ("clientInvoiceId", client_invoice_id)
    ]
    assert b"%26" in request.url.query and b"%23" in request.url.query
    assert request.headers["authorization"] == "Bearer synthetic-address-token"
    assert request.headers["content-type"] == "application/json"
    assert "idempotency-key" not in request.headers
    assert "Rocket-Pay-Key" not in request.headers
    assert json.loads(request.content) == {"payNetwork": network}
    assert body.model_fields_set == original_fields
    assert isinstance(result, InvoicePaymentAddress)
    assert result.address == ADDRESS["address"]
    assert result.pay_currency == "USDT"
    assert result.pay_network == "future_network"
    assert result.expires_at.utcoffset() == timedelta(hours=5, minutes=30)
    assert result.expires_at.microsecond == 123456
    assert result.min_amount.as_tuple() == Decimal(ADDRESS["minAmount"]).as_tuple()
    assert result.model_extra == {"futureResponseField": {"preserved": True}}


@pytest.mark.parametrize(
    "ids",
    [
        {"invoice_id": "0"},
        {"client_invoice_id": "0"},
        {"invoice_id": "ю" * 100},
        {"client_invoice_id": "ю" * 100},
    ],
)
async def test_either_identifier_accepts_literal_documented_length_boundaries(
    asynchronous: bool, ids: dict[str, str]
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json=ADDRESS)

    async with _client(asynchronous, respond) as client:
        await _resolve(
            client.invoices.create_payment_address(
                request=InvoiceCreatePaymentAddressRequest(pay_network="TON"), **ids
            )
        )
    aliases = {"invoice_id": "invoiceId", "client_invoice_id": "clientInvoiceId"}
    assert len(calls) == 1
    assert calls[0].url.params.multi_items() == [
        (aliases[key], value) for key, value in ids.items()
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"payNetwork": None},
        {"payNetwork": ""},
        {"payNetwork": "ton"},
        {"payNetwork": "FUTURE"},
        {"payNetwork": 1},
        {"payNetwork": True},
        {"payNetwork": b"TON"},
        {"payNetwork": ["TON"]},
        {"payNetwork": "TON", "invoiceId": "synthetic-invoice"},
        {"payNetwork": "TON", "client_invoice_id": "synthetic-client-invoice"},
        {"payNetwork": "TON", "futureResponseField": True},
    ],
)
def test_request_requires_strict_documented_network_and_forbids_extra_fields(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        InvoiceCreatePaymentAddressRequest.model_validate(payload)


@pytest.mark.parametrize("key", ["pay_network", "payNetwork"])
def test_python_and_wire_names_serialize_only_the_camel_case_body(key: str) -> None:
    body = InvoiceCreatePaymentAddressRequest.model_validate({key: "TON"})
    assert json.loads(serialize_request(body)) == {"payNetwork": "TON"}


@pytest.mark.parametrize(
    "factory",
    [
        lambda: {"payNetwork": "TON"},
        lambda: InvoicePaymentAddress.model_validate(ADDRESS),
        lambda: InvoiceCreateRequest(price_currency="USDT"),
        lambda: None,
    ],
)
async def test_resource_rejects_other_request_types_before_io(
    asynchronous: bool, factory: Callable[[], Any]
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json=ADDRESS)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(TypeError):
            await _resolve(
                client.invoices.create_payment_address(
                    request=factory(), invoice_id="synthetic-invoice"
                )
            )
    assert calls == []


@pytest.mark.parametrize("value", [None, "", "ton", "FUTURE", 1, True])
@pytest.mark.parametrize("constructed", [False, True], ids=["mutated", "constructed"])
async def test_bypassed_request_network_is_revalidated_before_io(
    asynchronous: bool, value: Any, constructed: bool
) -> None:
    calls: list[httpx.Request] = []
    if constructed:
        body = InvoiceCreatePaymentAddressRequest.model_construct(pay_network=value)
    else:
        body = InvoiceCreatePaymentAddressRequest(pay_network="TON")
        body.pay_network = value

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json=ADDRESS)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(ValidationError):
            await _resolve(
                client.invoices.create_payment_address(request=body, invoice_id="synthetic-invoice")
            )
    assert calls == []


async def test_constructed_request_without_required_network_fails_before_io(
    asynchronous: bool,
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json=ADDRESS)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(ValidationError):
            await _resolve(
                client.invoices.create_payment_address(
                    request=InvoiceCreatePaymentAddressRequest.model_construct(),
                    invoice_id="synthetic-invoice",
                )
            )
    assert calls == []


async def test_required_network_survives_empty_fields_set_without_mutating_request(
    asynchronous: bool,
) -> None:
    calls: list[httpx.Request] = []
    body = InvoiceCreatePaymentAddressRequest.model_construct(_fields_set=set(), pay_network="TON")

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json=ADDRESS)

    async with _client(asynchronous, respond) as client:
        await _resolve(
            client.invoices.create_payment_address(request=body, invoice_id="synthetic-invoice")
        )
    assert len(calls) == 1
    assert json.loads(calls[0].content) == {"payNetwork": "TON"}
    assert body.model_fields_set == set()


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
async def test_invalid_identifiers_fail_before_io(
    asynchronous: bool, ids: dict[str, Any]
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json=ADDRESS)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(ValueError):
            await _resolve(
                client.invoices.create_payment_address(
                    request=InvoiceCreatePaymentAddressRequest(pay_network="TON"), **ids
                )
            )
    assert calls == []


async def test_response_minimum_may_be_omitted(asynchronous: bool) -> None:
    payload = {key: value for key, value in ADDRESS.items() if key != "minAmount"}
    async with _client(asynchronous, lambda _: httpx.Response(201, json=payload)) as client:
        result = await _create(client)
    assert result.min_amount is None
    assert "min_amount" not in result.model_fields_set
    assert "minAmount" not in result.model_dump(by_alias=True, exclude_unset=True)


@pytest.mark.parametrize("amount", [0, "-0.0000", "1E-40"])
async def test_response_minimum_preserves_zero_sign_scale_and_small_values(
    asynchronous: bool, amount: int | str
) -> None:
    async with _client(
        asynchronous, lambda _: httpx.Response(201, json={**ADDRESS, "minAmount": amount})
    ) as client:
        result = await _create(client)
    assert result.min_amount.as_tuple() == Decimal(amount).as_tuple()


@pytest.mark.parametrize("field", ["address", "payCurrency", "payNetwork", "expiresAt"])
@pytest.mark.parametrize("missing", [False, True], ids=["null", "missing"])
async def test_required_response_fields_reject_missing_and_null(
    asynchronous: bool, field: str, missing: bool
) -> None:
    payload: dict[str, Any] = dict(ADDRESS)
    if missing:
        del payload[field]
    else:
        payload[field] = None
    async with _client(asynchronous, lambda _: httpx.Response(201, json=payload)) as client:
        with pytest.raises(ResponseValidationError):
            await _create(client)


@pytest.mark.parametrize(
    "field,value",
    [
        ("address", 1),
        ("payCurrency", []),
        ("payNetwork", True),
        ("expiresAt", "2026-10-17T08:00:00"),
        ("expiresAt", "not a datetime"),
        ("expiresAt", {}),
        ("minAmount", None),
        ("minAmount", 0.1),
        ("minAmount", True),
        ("minAmount", "NaN"),
        ("minAmount", "Infinity"),
        ("minAmount", "invalid"),
    ],
)
async def test_invalid_response_values_use_response_validation_errors(
    asynchronous: bool, field: str, value: Any
) -> None:
    async with _client(
        asynchronous, lambda _: httpx.Response(201, json={**ADDRESS, field: value})
    ) as client:
        with pytest.raises(ResponseValidationError):
            await _create(client)


@pytest.mark.parametrize("status", [200, 202, 204])
async def test_only_documented_201_is_accepted(asynchronous: bool, status: int) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=ADDRESS)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(ResponseValidationError):
            await _create(client)
    assert len(calls) == 1


@pytest.mark.parametrize("content", [b"", b"null", b"{}", b"[]", b"true", b"not json"])
async def test_malformed_success_uses_response_validation_error(
    asynchronous: bool, content: bytes
) -> None:
    async with _client(
        asynchronous, lambda _: httpx.Response(201, content=content)
    ) as client:
        with pytest.raises(ResponseValidationError):
            await _create(client)


async def test_sdk_auth_is_required_before_io_despite_injected_session_defaults(
    asynchronous: bool,
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json=ADDRESS)

    async with _client(
        asynchronous,
        respond,
        token=None,
        headers={"authorization": "Bearer unrelated-default"},
        auth=("unrelated-user", "unrelated-password"),
    ) as client:
        with pytest.raises(AuthenticationError):
            await _create(client)
    assert calls == []


@pytest.mark.parametrize(
    "status,error",
    [
        (400, APIError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (429, RateLimitError),
        (500, ServerError),
    ],
)
async def test_errors_preserve_problem_metadata_without_retry(
    asynchronous: bool, status: int, error: type[APIError]
) -> None:
    calls: list[httpx.Request] = []
    problem = {
        "type": "/api/problems/synthetic_address_problem",
        "status": status,
        "detail": "Synthetic problem",
        "future": {"preserved": True},
    }

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            json=problem,
            headers={"x-request-id": "synthetic-address-request", "retry-after": "9"},
        )

    async with _client(asynchronous, respond) as client:
        with pytest.raises(error) as caught:
            await _create(client)
    assert len(calls) == 1
    assert caught.value.status_code == status
    assert caught.value.problem == problem
    assert caught.value.request_id == "synthetic-address-request"
    assert caught.value.retry_after == "9"


async def test_timeout_is_wrapped_without_retry(asynchronous: bool) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(RequestTimeoutError):
            await _create(client)
    assert len(calls) == 1


async def test_redirect_is_not_followed_even_with_session_opt_in(asynchronous: bool) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(307, headers={"location": "https://other.invalid/sink"})

    async with _client(asynchronous, respond, follow_redirects=True) as client:
        with pytest.raises(APIError) as caught:
            await _create(client)
    assert caught.value.status_code == 307
    assert len(calls) == 1


def test_public_exports_and_keyword_only_sync_async_contracts_match() -> None:
    for name in ("InvoiceCreatePaymentAddressRequest", "InvoicePaymentAddress"):
        assert getattr(pay, name) is getattr(models, name)
        assert name in pay.__all__
        assert name in models.__all__
    assert issubclass(InvoiceCreatePaymentAddressRequest, RequestModel)
    assert not issubclass(InvoicePaymentAddress, RequestModel)
    sync = inspect.signature(InvoicesResource.create_payment_address)
    asynchronous = inspect.signature(AsyncInvoicesResource.create_payment_address)
    assert sync == asynchronous
    assert sync.return_annotation is InvoicePaymentAddress
    assert set(sync.parameters) == {"self", "request", "invoice_id", "client_invoice_id"}
    assert sync.parameters["request"].annotation is InvoiceCreatePaymentAddressRequest
    assert sync.parameters["request"].default is inspect.Parameter.empty
    for name in ("invoice_id", "client_invoice_id"):
        assert sync.parameters[name].default is None
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for name, parameter in sync.parameters.items()
        if name != "self"
    )


def test_request_response_and_operation_contracts_match_saved_current_oas() -> None:
    snapshot = json.loads(
        (Path(__file__).parents[1] / "spec" / "openapi" / "pay-current.json").read_text(
            encoding="utf-8"
        )
    )
    schemas = snapshot["components"]["schemas"]
    request_schema = schemas["InvoiceCreatePaymentAddressRequestDto"]
    response_schema = schemas["InvoicePaymentAddressResponseDto"]
    for model, schema in (
        (InvoiceCreatePaymentAddressRequest, request_schema),
        (InvoicePaymentAddress, response_schema),
    ):
        assert {field.alias for field in model.model_fields.values()} == set(schema["properties"])
        assert {
            field.alias for field in model.model_fields.values() if field.is_required()
        } == set(schema["required"])
    assert request_schema["required"] == ["payNetwork"]
    assert request_schema["properties"]["payNetwork"]["enum"] == [
        "TON", "BSC", "ETH", "BTC", "TRX", "SOL"
    ]
    assert response_schema["properties"]["expiresAt"]["type"] == "string"
    assert response_schema["properties"]["expiresAt"]["format"] == "date-time"
    assert "enum" not in response_schema["properties"]["payNetwork"]
    assert not response_schema["properties"]["minAmount"].get("nullable", False)
    operation = snapshot["paths"]["/api/v1/invoices/payments/address"]["post"]
    assert {status for status in operation["responses"] if status.startswith("2")} == {"201"}
    assert operation["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/InvoicePaymentAddressResponseDto"
    }
    assert operation["requestBody"]["required"] is True
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/InvoiceCreatePaymentAddressRequestDto"
    }
    assert {
        (parameter["name"], parameter["in"], parameter["schema"]["maxLength"])
        for parameter in operation["parameters"]
    } == {("invoiceId", "query", 100), ("clientInvoiceId", "query", 100)}
    assert operation["security"] == [{"bearer": []}]
