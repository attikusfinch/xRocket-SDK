"""Offline contracts for Current Pay cheque creation, updates, and deletion."""

import inspect
import json
import logging
import traceback
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

import xrocket.pay as pay
import xrocket.pay.models as models
from xrocket import (
    APIError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ResponseValidationError,
    ServerError,
)
from xrocket._core.serialization import RequestModel, serialize_request
from xrocket.pay import (
    AsyncPayClient,
    Cheque,
    ChequeCallback,
    ChequeCallbackRequest,
    ChequeCreateRequest,
    ChequeUpdateRequest,
    ChequeURLRequest,
    PayClient,
)
from xrocket.pay.resources.cheques import AsyncChequesResource, ChequesResource

CHEQUE = {
    "chequeId": "synthetic-cheque",
    "asset": "USDT",
    "links": {"webLink": "https://example.invalid/cheque", "futureLink": True},
    "deleted": False,
    "state": "a_future_cheque_state",
    "futureResponseField": {"retained": True},
}
PASSWORD = "synthetic-password-marker"
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
    token: str | None = "synthetic-cheque-token",
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
            client.cheques.create(request=ChequeCreateRequest(asset="USDT", amount="1"))
        )
    if operation == "update":
        return await _resolve(
            client.cheques.update(
                request=ChequeUpdateRequest(description="Updated"), cheque_id="synthetic-cheque"
            )
        )
    return await _resolve(client.cheques.delete(cheque_id="synthetic-cheque"))


@pytest.mark.parametrize(
    "operation,kwargs,method,query,body",
    [
        (
            "create",
            {"request": ChequeCreateRequest(asset="USDT", amount="1.2300")},
            "POST",
            {},
            {"asset": "USDT", "amount": "1.2300"},
        ),
        (
            "update",
            {"request": ChequeUpdateRequest(), "cheque_id": "000 /+?&ю"},
            "PUT",
            {"chequeId": "000 /+?&ю"},
            {},
        ),
        (
            "update",
            {"request": ChequeUpdateRequest(description=""), "client_cheque_id": "c" * 100},
            "PUT",
            {"clientChequeId": "c" * 100},
            {"description": ""},
        ),
        (
            "update",
            {
                "request": ChequeUpdateRequest(description="Updated 🎁"),
                "cheque_id": "cheque",
                "client_cheque_id": "client +/= &?%#ю",
            },
            "PUT",
            {"chequeId": "cheque", "clientChequeId": "client +/= &?%#ю"},
            {"description": "Updated 🎁"},
        ),
        ("delete", {"cheque_id": "000 /+?&ю"}, "DELETE", {"chequeId": "000 /+?&ю"}, None),
        (
            "delete",
            {"client_cheque_id": "c" * 100},
            "DELETE",
            {"clientChequeId": "c" * 100},
            None,
        ),
        (
            "delete",
            {"cheque_id": "c" * 100, "client_cheque_id": "client"},
            "DELETE",
            {"chequeId": "c" * 100, "clientChequeId": "client"},
            None,
        ),
    ],
)
async def test_mutations_use_plural_routes_and_separate_query_from_body(
    asynchronous: bool,
    operation: str,
    kwargs: dict[str, Any],
    method: str,
    query: dict[str, str],
    body: dict[str, Any] | None,
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200) if operation == "delete" else httpx.Response(200, json=CHEQUE)

    async with _client(asynchronous, respond) as client:
        result = await _resolve(getattr(client.cheques, operation)(**kwargs))

    assert len(calls) == 1
    request = calls[0]
    assert request.method == method
    assert request.url.host == "pay.api.testnet.xrocket.exchange"
    assert request.url.path == "/api/v1/cheques"
    assert dict(request.url.params) == query
    assert request.headers["authorization"] == "Bearer synthetic-cheque-token"
    assert request.headers["accept"] == "application/json"
    assert "idempotency-key" not in request.headers
    assert "Rocket-Pay-Key" not in request.headers
    if body is None:
        assert request.content == b""
        assert "content-type" not in request.headers
        assert result is None
    else:
        assert request.headers["content-type"] == "application/json"
        assert json.loads(request.content) == body
        assert isinstance(result, Cheque)
        assert result.cheque_id == "synthetic-cheque"
        assert result.state == "a_future_cheque_state"
        assert result.model_extra == {"futureResponseField": {"retained": True}}
        assert result.links.model_extra == {"futureLink": True}


async def test_create_sends_every_documented_field_with_exact_amount_and_password(
    asynchronous: bool,
) -> None:
    amount = Decimal("12345678901234567890.12345678900000000001")
    body = ChequeCreateRequest(
        client_cheque_id="client +/= &?%#ю",
        asset="USDT",
        amount=amount,
        password=PASSWORD,
        description="Заказ 🎁",
        callback=ChequeCallbackRequest(
            callback_url="https://example.invalid/callback",
            payload={"custom": [None, True, Decimal("0.0000000000000000001")]},
        ),
        url=ChequeURLRequest(
            success_url="https://example.invalid/success",
            cancel_url="https://example.invalid/cancel",
        ),
        target_type="telegram_user_id",
        target="000123",
    )
    original_fields = body.model_fields_set.copy()
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=CHEQUE)

    async with _client(asynchronous, respond) as client:
        await _resolve(client.cheques.create(request=body))

    assert len(calls) == 1
    assert json.loads(calls[0].content) == {
        "clientChequeId": "client +/= &?%#ю",
        "asset": "USDT",
        "amount": str(amount),
        "password": PASSWORD,
        "description": "Заказ 🎁",
        "callback": {
            "callbackUrl": "https://example.invalid/callback",
            "payload": {"custom": [None, True, "1E-19"]},
        },
        "url": {
            "successUrl": "https://example.invalid/success",
            "cancelUrl": "https://example.invalid/cancel",
        },
        "targetType": "telegram_user_id",
        "target": "000123",
    }
    assert not calls[0].url.query
    assert body.model_fields_set == original_fields
    assert body.amount.as_tuple() == amount.as_tuple()
    assert isinstance(body.password, SecretStr)
    assert body.password.get_secret_value() == PASSWORD


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"asset": "USDT", "amount": "0"}, {"asset": "USDT", "amount": "0"}),
        (
            {
                "asset": "",
                "amount": "-0.0000",
                "clientChequeId": "",
                "password": "",
                "description": "",
                "targetType": "user_id",
                "target": "",
                "callback": {"callbackUrl": "", "payload": {}},
                "url": {"successUrl": "", "cancelUrl": ""},
            },
            {
                "asset": "",
                "amount": "-0.0000",
                "clientChequeId": "",
                "password": "",
                "description": "",
                "targetType": "user_id",
                "target": "",
                "callback": {"callbackUrl": "", "payload": {}},
                "url": {"successUrl": "", "cancelUrl": ""},
            },
        ),
        (
            {"asset": "USDT", "amount": "1", "callback": {}, "url": {}},
            {"asset": "USDT", "amount": "1", "callback": {}, "url": {}},
        ),
    ],
)
def test_create_preserves_omission_explicit_empty_values_and_camel_aliases(
    payload: dict[str, Any], expected: dict[str, Any]
) -> None:
    assert json.loads(serialize_request(ChequeCreateRequest.model_validate(payload))) == expected


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
def test_amount_is_an_exact_finite_decimal_without_invented_range(amount: str | Decimal) -> None:
    body = ChequeCreateRequest.model_validate({"asset": "USDT", "amount": amount})
    assert body.amount.as_tuple() == Decimal(amount).as_tuple()
    assert json.loads(serialize_request(body))["amount"] == str(Decimal(amount))


@pytest.mark.parametrize(
    "amount", [0, 1, 0.1, True, False, None, b"1", "", "invalid", "NaN", "Infinity", Decimal("NaN")]
)
def test_amount_rejects_coercion_and_non_finite_values(amount: Any) -> None:
    with pytest.raises(ValidationError):
        ChequeCreateRequest.model_validate({"asset": "USDT", "amount": amount})


@pytest.mark.parametrize(
    "changes",
    [
        {"asset": None},
        {"asset": 123},
        {"client_cheque_id": 123},
        {"description": 123},
        {"password": 123},
        {"password": b"password"},
        {"callback": []},
        {"callback": {"payload": []}},
        {"url": []},
        {"target_type": "future_target", "target": "000123"},
        {"target_type": "user_id"},
        {"target": "000123"},
        {"target_type": "user_id", "target": 123},
    ],
)
def test_create_rejects_invalid_types_and_unpaired_or_unknown_targets(
    changes: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        ChequeCreateRequest.model_validate({"asset": "USDT", "amount": "1", **changes})


@pytest.mark.parametrize("missing", ["asset", "amount"])
def test_create_requires_exactly_the_documented_required_fields(missing: str) -> None:
    payload = {"asset": "USDT", "amount": "1"}
    del payload[missing]
    with pytest.raises(ValidationError):
        ChequeCreateRequest.model_validate(payload)


@pytest.mark.parametrize("target_type", ["user_id", "telegram_user_id", "telegram_username"])
def test_create_accepts_every_documented_request_target_type(target_type: str) -> None:
    body = ChequeCreateRequest.model_validate(
        {"asset": "unknown future asset", "amount": "1", "targetType": target_type, "target": ""}
    )
    assert json.loads(serialize_request(body))["targetType"] == target_type


@pytest.mark.parametrize(
    "model,field,maximum",
    [
        (ChequeCreateRequest, "client_cheque_id", 50),
        (ChequeCreateRequest, "password", 100),
        (ChequeCreateRequest, "description", 1000),
        (ChequeCreateRequest, "target", 100),
        (ChequeUpdateRequest, "description", 1000),
        (ChequeCallbackRequest, "callback_url", 500),
        (ChequeURLRequest, "success_url", 500),
        (ChequeURLRequest, "cancel_url", 500),
    ],
)
def test_request_string_lengths_follow_schema(model: Any, field: str, maximum: int) -> None:
    required = {"asset": "USDT", "amount": "1"} if model is ChequeCreateRequest else {}
    if field == "target":
        required["target_type"] = "user_id"
    body = model.model_validate({**required, field: "ю" * maximum})
    value = getattr(body, field)
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    assert value == "ю" * maximum
    with pytest.raises(ValidationError):
        model.model_validate({**required, field: "ю" * (maximum + 1)})


@pytest.mark.parametrize(
    "model,field",
    [
        *(
            (ChequeCreateRequest, field)
            for field in (
                "client_cheque_id",
                "password",
                "description",
                "callback",
                "url",
                "target_type",
                "target",
            )
        ),
        (ChequeUpdateRequest, "description"),
        (ChequeCallbackRequest, "callback_url"),
        (ChequeCallbackRequest, "payload"),
        (ChequeURLRequest, "success_url"),
        (ChequeURLRequest, "cancel_url"),
    ],
)
def test_optional_fields_allow_omission_and_reject_explicit_null(model: Any, field: str) -> None:
    required = {"asset": "USDT", "amount": "1"} if model is ChequeCreateRequest else {}
    assert json.loads(serialize_request(model.model_validate(required))) == required
    with pytest.raises(ValidationError):
        model.model_validate({**required, field: None})


@pytest.mark.parametrize("description", [None, 0, True, "x" * 1001])
def test_update_rejects_null_coercion_and_overlong_description(description: Any) -> None:
    with pytest.raises(ValidationError):
        ChequeUpdateRequest.model_validate({"description": description})


@pytest.mark.parametrize(
    "model", [ChequeCreateRequest, ChequeUpdateRequest, ChequeCallbackRequest, ChequeURLRequest]
)
def test_request_models_forbid_response_extras(model: Any) -> None:
    required = {"asset": "USDT", "amount": "1"} if model is ChequeCreateRequest else {}
    with pytest.raises(ValidationError):
        model.model_validate({**required, "futureResponseField": True})


@pytest.mark.parametrize("field", ["asset", "amount", "password", "target", "callback", "chequeId"])
def test_update_does_not_accept_create_response_or_identifier_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        ChequeUpdateRequest.model_validate({field: "synthetic"})


@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize(
    "identifiers",
    [
        {},
        *(
            {field: value}
            for field in ("cheque_id", "client_cheque_id")
            for value in ("", "x" * 101, 123, True)
        ),
        {"cheque_id": "valid", "client_cheque_id": ""},
        {"cheque_id": "", "client_cheque_id": "valid"},
    ],
)
async def test_invalid_identifiers_fail_before_network(
    asynchronous: bool, operation: str, identifiers: dict[str, Any]
) -> None:
    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid cheque identifiers reached the network")

    kwargs = (
        {"request": ChequeUpdateRequest(), **identifiers} if operation == "update" else identifiers
    )
    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValueError):
            await _resolve(getattr(client.cheques, operation)(**kwargs))


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("kind", ["mapping", "response", "wrong_request", "null"])
async def test_mutations_require_their_specific_request_model_before_network(
    asynchronous: bool, operation: str, kind: str
) -> None:
    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("A non-cheque request model reached the network")

    bodies = {
        "mapping": {"asset": "USDT", "amount": "1"},
        "response": Cheque.model_validate(CHEQUE),
        "wrong_request": ChequeURLRequest(),
        "null": None,
    }
    kwargs = {"request": bodies[kind]}
    if operation == "update":
        kwargs["cheque_id"] = "synthetic"
    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(TypeError):
            await _resolve(getattr(client.cheques, operation)(**kwargs))


@pytest.mark.parametrize(
    "operation,field,value",
    [
        ("create", "amount", 0.1),
        ("create", "client_cheque_id", "x" * 51),
        ("create", "description", None),
        ("create", "password", "x" * 101),
        ("create", "target_type", "future_target"),
        ("create", "target", "000123"),
        ("update", "description", None),
        ("update", "description", "x" * 1001),
    ],
)
@pytest.mark.parametrize("constructed", [False, True], ids=["mutated", "constructed"])
async def test_bypassed_request_validation_is_rechecked_before_network(
    asynchronous: bool, operation: str, field: str, value: Any, constructed: bool
) -> None:
    required = {"asset": "USDT", "amount": "1"} if operation == "create" else {}
    model = ChequeCreateRequest if operation == "create" else ChequeUpdateRequest
    if constructed:
        body = model.model_construct(**{**required, field: value})
    else:
        body = model.model_validate(required)
        setattr(body, field, value)

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An invalid mutated cheque request reached the network")

    kwargs = {"request": body}
    if operation == "update":
        kwargs["cheque_id"] = "synthetic"
    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(getattr(client.cheques, operation)(**kwargs))


async def test_nested_request_validation_and_response_model_boundaries_are_rechecked(
    asynchronous: bool,
) -> None:
    body = ChequeCreateRequest(asset="USDT", amount="1", callback=ChequeCallbackRequest())
    assert body.callback is not None
    body.callback.callback_url = "x" * 501

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An invalid nested cheque request reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.cheques.create(request=body))
        body.callback = ChequeCallbackRequest(
            payload={"response": ChequeCallback.model_validate({"callbackUrl": "synthetic"})}
        )
        with pytest.raises(TypeError):
            await _resolve(client.cheques.create(request=body))


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_mutations_require_sdk_authentication_before_network(
    asynchronous: bool, operation: str
) -> None:
    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An unauthenticated cheque mutation reached the network")

    async with _client(asynchronous, unexpected, token=None) as client:
        with pytest.raises(AuthenticationError):
            await _write(client, operation)


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
@pytest.mark.parametrize("status", [201, 202, 204])
async def test_mutations_only_accept_the_documented_200_status(
    asynchronous: bool, operation: str, status: int
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return (
            httpx.Response(status, json=CHEQUE) if operation != "delete" else httpx.Response(status)
        )

    async with _client(asynchronous, respond) as client:
        with pytest.raises(ResponseValidationError):
            await _write(client, operation)
    assert len(calls) == 1


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("content", [b"", b"null", b"{}", b"[]", b"not json"])
async def test_create_and_update_require_a_valid_cheque_response(
    asynchronous: bool, operation: str, content: bytes
) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(200, content=content)) as client:
        with pytest.raises(ResponseValidationError):
            await _write(client, operation)


@pytest.mark.parametrize("content", [b" ", b"null", b"{}", b"[]", b"true"])
async def test_delete_requires_a_strictly_empty_200_body(
    asynchronous: bool, content: bytes
) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(200, content=content)) as client:
        with pytest.raises(ResponseValidationError):
            await _write(client, "delete")


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
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
async def test_mutation_errors_preserve_metadata_without_retry(
    asynchronous: bool, operation: str, status: int, error: type[APIError]
) -> None:
    calls: list[httpx.Request] = []
    problem = {"status": status, "detail": "Synthetic problem", "future": {"retained": True}}

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            json=problem,
            headers={"x-request-id": "synthetic-cheque-request", "retry-after": "9"},
        )

    async with _client(asynchronous, respond) as client:
        with pytest.raises(error) as caught:
            await _write(client, operation)
    assert type(caught.value) is error
    assert caught.value.status_code == status
    assert caught.value.problem == problem
    assert caught.value.request_id == "synthetic-cheque-request"
    assert caught.value.retry_after == "9"
    assert len(calls) == 1


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_mutations_do_not_follow_redirects(asynchronous: bool, operation: str) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(307, headers={"location": "https://other.invalid/sink"})

    async with _client(asynchronous, respond, follow_redirects=True) as client:
        with pytest.raises(APIError) as caught:
            await _write(client, operation)
    assert caught.value.status_code == 307
    assert len(calls) == 1


def test_password_is_secret_in_ordinary_representation_and_dumps(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = ChequeCreateRequest(asset="USDT", amount="1", password=PASSWORD)
    representations = [repr(body), str(body), repr(body.model_dump()), body.model_dump_json()]
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("synthetic.cheque").debug("Request %r %s", body, body.model_dump_json())
    assert PASSWORD not in " ".join(representations)
    assert PASSWORD not in caplog.text
    assert json.loads(serialize_request(body))["password"] == PASSWORD


@pytest.mark.parametrize("constructed", [False, True])
def test_json_dump_masks_password_after_bypassing_validation(constructed: bool) -> None:
    if constructed:
        body = ChequeCreateRequest.model_construct(
            asset="USDT", amount=Decimal("1"), password=PASSWORD
        )
    else:
        body = ChequeCreateRequest(asset="USDT", amount="1")
        body.password = PASSWORD
    assert PASSWORD not in repr(body)
    assert PASSWORD not in repr(body.model_dump())
    assert PASSWORD not in body.model_dump_json()
    assert json.loads(serialize_request(body))["password"] == PASSWORD


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": "invalid"},
        {"target": "orphan"},
        {"password": PASSWORD * 5},
        {"callback": {"callbackUrl": "x" * 501}},
        {"unexpected": PASSWORD},
    ],
)
def test_password_is_absent_from_validation_error_representations(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError) as caught:
        ChequeCreateRequest.model_validate(
            {"asset": "USDT", "amount": "1", "password": PASSWORD, **changes}
        )
    error = caught.value
    assert PASSWORD not in str(error)
    assert PASSWORD not in repr(error)
    assert PASSWORD not in repr(error.errors())
    assert PASSWORD not in error.json()


@pytest.mark.parametrize("failure", ["validation", "api", "response"])
async def test_password_stays_out_of_errors_and_http_logs(
    asynchronous: bool, failure: str, caplog: pytest.LogCaptureFixture
) -> None:
    body = ChequeCreateRequest(asset="USDT", amount="1", password=PASSWORD)
    calls: list[httpx.Request] = []
    if failure == "validation":
        body.target = "orphan"

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return (
            httpx.Response(400, json={"detail": PASSWORD})
            if failure == "api"
            else httpx.Response(200, json={"password": PASSWORD})
        )

    error_type = {
        "validation": ValidationError,
        "api": APIError,
        "response": ResponseValidationError,
    }[failure]
    with caplog.at_level(logging.DEBUG):
        async with _client(asynchronous, respond) as client:
            with pytest.raises(error_type) as caught:
                await _resolve(client.cheques.create(request=body))
    assert PASSWORD not in str(caught.value)
    assert PASSWORD not in repr(caught.value)
    assert PASSWORD not in caplog.text
    if isinstance(caught.value, ValidationError):
        assert PASSWORD not in repr(caught.value.errors())
        assert PASSWORD not in caught.value.json()
    assert len(calls) == (0 if failure == "validation" else 1)


@pytest.mark.parametrize("location", ["callback_text", "callback_key", "password"])
@pytest.mark.parametrize("surrogate", [chr(0xD800), chr(0xDFFF)], ids=["high", "low"])
async def test_invalid_unicode_cannot_expose_password_through_encoding_errors(
    asynchronous: bool,
    location: str,
    surrogate: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    password = PASSWORD + surrogate if location == "password" else PASSWORD
    payload = (
        {"nested": [{"text": surrogate}]}
        if location == "callback_text"
        else {"nested": [{surrogate: "synthetic"}]}
        if location == "callback_key"
        else {}
    )
    body = ChequeCreateRequest(
        asset="USDT",
        amount="1",
        password=password,
        callback=ChequeCallbackRequest(payload=payload),
    )
    calls: list[httpx.Request] = []

    def unexpected(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        pytest.fail("A cheque request containing an unpaired surrogate reached the network")

    with caplog.at_level(logging.DEBUG):
        async with _client(asynchronous, unexpected) as client:
            with pytest.raises(ValueError) as caught:
                await _resolve(client.cheques.create(request=body))
        error = caught.value
        logging.getLogger("synthetic.cheque").error(
            "Cheque request rejected", exc_info=(type(error), error, error.__traceback__)
        )

    assert type(error) is ValueError
    assert calls == []
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        representations = [
            str(current),
            repr(current),
            repr(current.args),
            repr(getattr(current, "object", None)),
            "".join(traceback.format_exception(current)),
        ]
        assert PASSWORD not in "\n".join(representations)
        pending.extend(
            nested for nested in (current.__cause__, current.__context__) if nested is not None
        )
    assert PASSWORD not in caplog.text


async def test_valid_unicode_and_astral_characters_preserve_wire_bytes(
    asynchronous: bool,
) -> None:
    text = "Заказ 東京 🎁 𐐷 e\u0301"
    body = ChequeCreateRequest(
        asset="USDT",
        amount=Decimal("123.4500"),
        password=PASSWORD + text,
        description=text,
        callback=ChequeCallbackRequest(payload={text: [text]}),
    )
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=CHEQUE)

    async with _client(asynchronous, respond) as client:
        result = await _resolve(client.cheques.create(request=body))

    assert isinstance(result, Cheque)
    assert len(calls) == 1
    assert text.encode("utf-8") in calls[0].content
    assert json.loads(calls[0].content.decode("utf-8")) == {
        "asset": "USDT",
        "amount": "123.4500",
        "password": PASSWORD + text,
        "description": text,
        "callback": {"payload": {text: [text]}},
    }


def test_public_request_exports_and_resource_signatures_are_symmetric() -> None:
    for name in (
        "ChequeCreateRequest",
        "ChequeUpdateRequest",
        "ChequeCallbackRequest",
        "ChequeURLRequest",
    ):
        assert name in pay.__all__
        assert name in models.__all__
        assert getattr(pay, name) is getattr(models, name)
        assert issubclass(getattr(pay, name), RequestModel)
    assert not issubclass(Cheque, RequestModel)
    assert not issubclass(ChequeCallback, RequestModel)
    for method in ("create", "update", "delete"):
        sync = inspect.signature(getattr(ChequesResource, method))
        asynchronous = inspect.signature(getattr(AsyncChequesResource, method))
        assert sync == asynchronous
        assert all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            for name, parameter in sync.parameters.items()
            if name != "self"
        )
    assert set(inspect.signature(ChequesResource.create).parameters) == {"self", "request"}
    assert set(inspect.signature(ChequesResource.update).parameters) == {
        "self",
        "request",
        "cheque_id",
        "client_cheque_id",
    }
    assert set(inspect.signature(ChequesResource.delete).parameters) == {
        "self",
        "cheque_id",
        "client_cheque_id",
    }


def test_request_fields_and_operation_policies_match_saved_current_oas() -> None:
    snapshot = json.loads(
        (Path(__file__).parents[1] / "spec" / "openapi" / "pay-current.json").read_text(
            encoding="utf-8"
        )
    )
    schemas = snapshot["components"]["schemas"]
    for model, schema_name in (
        (ChequeCreateRequest, "ChequeCreateRequestDto"),
        (ChequeUpdateRequest, "ChequeUpdateRequestDto"),
        (ChequeCallbackRequest, "ChequeCallbackRequestDto"),
        (ChequeURLRequest, "ChequeUrlRequestDto"),
    ):
        assert {field.alias for field in model.model_fields.values()} == set(
            schemas[schema_name]["properties"]
        )
    assert schemas["ChequeCreateRequestDto"]["required"] == ["asset", "amount"]
    for verb in ("post", "put", "delete"):
        operation = snapshot["paths"]["/api/v1/cheques"][verb]
        assert set(operation["responses"]) & {"200", "201", "202", "204"} == {"200"}
        if verb == "delete":
            assert "content" not in operation["responses"]["200"]
            assert "requestBody" not in operation
        if verb != "post":
            assert {
                (p["name"], p["in"], p["schema"]["maxLength"]) for p in operation["parameters"]
            } == {("chequeId", "query", 100), ("clientChequeId", "query", 100)}
