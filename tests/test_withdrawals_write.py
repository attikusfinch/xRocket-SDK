"""Offline withdrawal creates preserve caller IDs and uncertain timeout outcomes."""

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
    PermissionDeniedError,
    RateLimitError,
    RequestTimeoutError,
    ResponseValidationError,
    ServerError,
)
from xrocket._core.serialization import RequestModel, serialize_request
from xrocket.pay import (
    AsyncPayClient,
    PayClient,
    Withdrawal,
    WithdrawalCallback,
    WithdrawalCallbackRequest,
    WithdrawalCreateRequest,
)
from xrocket.pay.resources.withdrawals import AsyncWithdrawalsResource, WithdrawalsResource

EXACT_AMOUNT = "12345678901234567890.1234567890123456789000"
REQUIRED = {
    "clientWithdrawalId": "saved-before-send",
    "network": "TON",
    "address": "synthetic-Mixed_CASE-address +/=",
    "asset": "USDT",
    "amount": "1.2300",
}
WITHDRAWAL = {
    "withdrawalId": "synthetic-withdrawal",
    "network": "future_network",
    "address": "synthetic-Mixed_CASE-address +/=",
    "asset": "USDT",
    "amount": EXACT_AMOUNT,
    "status": "future_status",
    "futureResponseField": {"retained": True},
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
    token: str | None = "synthetic-withdrawal-token",
    **http_options: Any,
) -> AsyncIterator[Any]:
    http_cls = httpx.AsyncClient if asynchronous else httpx.Client
    client_cls = AsyncPayClient if asynchronous else PayClient
    http = http_cls(transport=httpx.MockTransport(handler), **http_options)
    client = client_cls(api_token=token, http_client=http, environment="testnet", timeout=12)
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


def _body(**changes: Any) -> WithdrawalCreateRequest:
    return WithdrawalCreateRequest.model_validate({**REQUIRED, **changes})


@pytest.mark.parametrize("all_fields", [False, True], ids=["minimal", "all-fields"])
async def test_create_sends_one_post_with_exact_money_and_open_withdrawal_response(
    asynchronous: bool, all_fields: bool
) -> None:
    changes = (
        {
            "clientWithdrawalId": "000-client +/= &?%#ю",
            "network": "ETH",
            "address": "  0xMiXeD-Case 東京 🎁  ",
            "asset": " usdt ",
            "amount": Decimal(EXACT_AMOUNT),
            "comment": "  Заказ 東京 🎁  ",
            "callback": WithdrawalCallbackRequest(
                callback_url="https://example.invalid/callback",
                payload={"custom": [None, True, Decimal("0.0000000000000000001")]},
            ),
        }
        if all_fields
        else {}
    )
    body = _body(**changes)
    fields_set = body.model_fields_set.copy()
    calls: list[httpx.Request] = []
    response = {
        **WITHDRAWAL,
        "callback": {
            "callbackUrl": "https://example.invalid/callback",
            "payload": {"synthetic": True},
            "futureCallbackField": 2,
        },
    }

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=response)

    async with _client(asynchronous, respond) as client:
        result = await _resolve(client.withdrawals.create(request=body))

    assert len(calls) == 1
    request = calls[0]
    assert request.method == "POST"
    assert str(request.url) == "https://pay.api.testnet.xrocket.exchange/api/v1/withdrawals"
    assert request.headers["authorization"] == "Bearer synthetic-withdrawal-token"
    assert request.headers["accept"] == "application/json"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["content-length"] == str(len(request.content))
    assert "idempotency-key" not in request.headers
    assert "Rocket-Pay-Key" not in request.headers
    expected = dict(REQUIRED)
    if all_fields:
        expected.update(
            clientWithdrawalId="000-client +/= &?%#ю",
            network="ETH",
            address="  0xMiXeD-Case 東京 🎁  ",
            asset=" usdt ",
            amount=EXACT_AMOUNT,
            comment="  Заказ 東京 🎁  ",
            callback={
                "callbackUrl": "https://example.invalid/callback",
                "payload": {"custom": [None, True, "1E-19"]},
            },
        )
        assert "  Заказ 東京 🎁  ".encode() in request.content
    assert json.loads(request.content) == expected
    assert body.model_fields_set == fields_set
    assert body.client_withdrawal_id == expected["clientWithdrawalId"]
    assert body.amount.as_tuple() == Decimal(expected["amount"]).as_tuple()
    assert isinstance(result, Withdrawal)
    assert result.withdrawal_id == "synthetic-withdrawal"
    assert result.amount.as_tuple() == Decimal(EXACT_AMOUNT).as_tuple()
    assert result.network == "future_network"
    assert result.status == "future_status"
    assert result.model_extra == {"futureResponseField": {"retained": True}}
    assert isinstance(result.callback, WithdrawalCallback)
    assert result.callback.model_extra == {"futureCallbackField": 2}
    assert result.callback.payload == {"synthetic": True}


@pytest.mark.parametrize("network", ["TON", "BSC", "ETH", "BTC", "TRX", "SOL"])
def test_all_documented_networks_preserve_schema_allowed_empty_strings(network: str) -> None:
    payload = {
        "clientWithdrawalId": "",
        "network": network,
        "address": "",
        "asset": "",
        "amount": "-0.0000",
        "comment": "",
        "callback": {"callbackUrl": "", "payload": {}},
    }
    assert json.loads(serialize_request(WithdrawalCreateRequest.model_validate(payload))) == payload


@pytest.mark.parametrize("callback", [{}, {"callbackUrl": ""}, {"payload": {}}])
def test_callback_properties_are_independently_optional(callback: dict[str, Any]) -> None:
    assert json.loads(serialize_request(_body(callback=callback))) == {
        **REQUIRED,
        "callback": callback,
    }


def test_snake_and_camel_input_aliases_have_identical_wire_output() -> None:
    snake = WithdrawalCreateRequest(
        client_withdrawal_id="saved-before-send",
        network="TON",
        address=REQUIRED["address"],
        asset="USDT",
        amount="1.2300",
        comment="Synthetic",
        callback=WithdrawalCallbackRequest(
            callback_url="https://example.invalid/callback", payload={}
        ),
    )
    camel = WithdrawalCreateRequest.model_validate(
        {
            **REQUIRED,
            "comment": "Synthetic",
            "callback": {"callbackUrl": "https://example.invalid/callback", "payload": {}},
        }
    )
    assert json.loads(serialize_request(snake)) == json.loads(serialize_request(camel))


@pytest.mark.parametrize("field", list(REQUIRED))
def test_every_schema_required_field_is_required_even_network_with_oas_default(field: str) -> None:
    payload = dict(REQUIRED)
    del payload[field]
    with pytest.raises(ValidationError):
        WithdrawalCreateRequest.model_validate(payload)


@pytest.mark.parametrize("field", list(REQUIRED))
def test_required_fields_do_not_accept_null(field: str) -> None:
    with pytest.raises(ValidationError):
        _body(**{field: None})


@pytest.mark.parametrize(
    "amount",
    [Decimal(EXACT_AMOUNT), "1E-40", Decimal("-0.0000"), "0", "-1.0000000000000000001"],
)
def test_money_has_no_invented_range_or_nine_decimal_place_truncation(
    amount: str | Decimal,
) -> None:
    body = _body(amount=amount)
    assert body.amount.as_tuple() == Decimal(amount).as_tuple()
    assert json.loads(serialize_request(body))["amount"] == str(Decimal(amount))


@pytest.mark.parametrize(
    "amount", [0, 1, 0.1, True, False, None, b"1", "", "invalid", "NaN", "Infinity", Decimal("NaN")]
)
def test_amount_rejects_coercion_and_non_finite_inputs(amount: Any) -> None:
    with pytest.raises(ValidationError):
        _body(amount=amount)


@pytest.mark.parametrize(
    "changes",
    [
        {"clientWithdrawalId": 123},
        {"clientWithdrawalId": True},
        {"network": 123},
        {"network": "ton"},
        {"network": "future_network"},
        {"address": 123},
        {"asset": 123},
        {"comment": 123},
        {"callback": []},
        {"callback": {"callbackUrl": 123}},
        {"callback": {"payload": []}},
        {"futureResponseField": True},
        {"callback": {"futureResponseField": True}},
    ],
)
def test_request_is_strict_and_forbids_response_extras(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _body(**changes)


@pytest.mark.parametrize(
    "model,field,maximum",
    [
        (WithdrawalCreateRequest, "clientWithdrawalId", 150),
        (WithdrawalCreateRequest, "address", 100),
        (WithdrawalCreateRequest, "comment", 50),
        (WithdrawalCallbackRequest, "callbackUrl", 500),
    ],
)
def test_string_maxima_count_characters_and_match_request_schema(
    model: Any, field: str, maximum: int
) -> None:
    required = REQUIRED if model is WithdrawalCreateRequest else {}
    valid = model.model_validate({**required, field: "ю" * maximum})
    assert json.loads(serialize_request(valid))[field] == "ю" * maximum
    with pytest.raises(ValidationError):
        model.model_validate({**required, field: "ю" * (maximum + 1)})


def test_asset_has_no_length_limit_borrowed_from_other_fields() -> None:
    body = _body(asset="x" * 1001)
    assert json.loads(serialize_request(body))["asset"] == "x" * 1001


@pytest.mark.parametrize(
    "model,field",
    [
        (WithdrawalCreateRequest, "comment"),
        (WithdrawalCreateRequest, "callback"),
        (WithdrawalCallbackRequest, "callbackUrl"),
        (WithdrawalCallbackRequest, "payload"),
    ],
)
def test_optional_properties_allow_omission_and_reject_explicit_null(
    model: Any, field: str
) -> None:
    required = REQUIRED if model is WithdrawalCreateRequest else {}
    assert json.loads(serialize_request(model.model_validate(required))) == required
    with pytest.raises(ValidationError):
        model.model_validate({**required, field: None})


@pytest.mark.parametrize("length", [0, 1, 100, 101, 150])
async def test_create_keeps_full_caller_id_without_generating_or_truncating(
    asynchronous: bool, length: int
) -> None:
    client_id = "ю" * length
    body = _body(clientWithdrawalId=client_id)
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=WITHDRAWAL)

    async with _client(asynchronous, respond) as client:
        await _resolve(client.withdrawals.create(request=body))
        if not 1 <= length <= 100:
            with pytest.raises(ValueError, match="1 to 100"):
                await _resolve(client.withdrawals.retrieve(client_withdrawal_id=client_id))

    assert len(calls) == 1
    assert json.loads(calls[0].content)["clientWithdrawalId"] == client_id
    assert body.client_withdrawal_id == client_id


@pytest.mark.parametrize("kind", ["mapping", "response", "wrong_request", "null"])
async def test_create_requires_specific_request_dto_before_io(
    asynchronous: bool, kind: str
) -> None:
    bodies = {
        "mapping": REQUIRED,
        "response": Withdrawal.model_validate(WITHDRAWAL),
        "wrong_request": WithdrawalCallbackRequest(),
        "null": None,
    }

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("A non-withdrawal request DTO reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(TypeError):
            await _resolve(client.withdrawals.create(request=bodies[kind]))


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", 0.1),
        ("client_withdrawal_id", "x" * 151),
        ("network", "future_network"),
        ("address", "x" * 101),
        ("comment", None),
        ("comment", "x" * 51),
    ],
)
@pytest.mark.parametrize("constructed", [False, True], ids=["mutated", "constructed"])
async def test_bypassed_validation_is_rechecked_before_io(
    asynchronous: bool, field: str, value: Any, constructed: bool
) -> None:
    if constructed:
        body = WithdrawalCreateRequest.model_construct(
            **{
                "client_withdrawal_id": "saved-before-send",
                "network": "TON",
                "address": "synthetic-address",
                "asset": "USDT",
                "amount": Decimal("1"),
                field: value,
            }
        )
    else:
        body = _body()
        setattr(body, field, value)

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An invalid mutated or constructed withdrawal reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.withdrawals.create(request=body))


@pytest.mark.parametrize("field", list(REQUIRED))
async def test_constructed_missing_required_field_is_revalidated_before_io(
    asynchronous: bool, field: str
) -> None:
    payload = {
        "client_withdrawal_id": "saved-before-send",
        "network": "TON",
        "address": "synthetic-address",
        "asset": "USDT",
        "amount": Decimal("1"),
    }
    snake_name = "client_withdrawal_id" if field == "clientWithdrawalId" else field
    del payload[snake_name]
    body = WithdrawalCreateRequest.model_construct(**payload)

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("A constructed withdrawal missing a required field reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.withdrawals.create(request=body))


async def test_nested_request_validation_and_model_boundaries_are_rechecked(
    asynchronous: bool,
) -> None:
    body = _body(callback=WithdrawalCallbackRequest())
    assert body.callback is not None
    body.callback.callback_url = "x" * 501

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An invalid nested withdrawal request reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.withdrawals.create(request=body))
        body.callback = WithdrawalCallbackRequest(
            payload={"response": Withdrawal.model_validate(WITHDRAWAL)}
        )
        with pytest.raises(TypeError):
            await _resolve(client.withdrawals.create(request=body))


async def test_create_requires_sdk_auth_before_io(asynchronous: bool) -> None:
    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An unauthenticated withdrawal reached the network")

    async with _client(asynchronous, unexpected, token=None) as client:
        with pytest.raises(AuthenticationError):
            await _resolve(client.withdrawals.create(request=_body()))


@pytest.mark.parametrize("status", [201, 202, 204])
async def test_create_accepts_only_documented_200(asynchronous: bool, status: int) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(status, json=WITHDRAWAL)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.withdrawals.create(request=_body()))


@pytest.mark.parametrize("content", [b"", b"null", b"{}", b"[]", b"not json"])
async def test_create_requires_a_valid_withdrawal_response(
    asynchronous: bool, content: bytes
) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(200, content=content)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.withdrawals.create(request=_body()))


@pytest.mark.parametrize(
    "changes", [{"amount": 0.1}, {"amount": "NaN"}, {"callback": {"payload": []}}]
)
async def test_malformed_response_fields_use_shared_error(
    asynchronous: bool, changes: dict[str, Any]
) -> None:
    async with _client(
        asynchronous, lambda _: httpx.Response(200, json={**WITHDRAWAL, **changes})
    ) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.withdrawals.create(request=_body()))


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
async def test_http_errors_preserve_problem_and_metadata_without_retry(
    asynchronous: bool, status: int, error: type[APIError]
) -> None:
    calls: list[httpx.Request] = []
    problem = {"status": status, "detail": "Synthetic problem", "future": {"retained": True}}

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status, json=problem, headers={"x-request-id": "withdrawal-request", "retry-after": "9"}
        )

    async with _client(asynchronous, respond) as client:
        with pytest.raises(error) as caught:
            await _resolve(client.withdrawals.create(request=_body()))
    assert type(caught.value) is error
    assert caught.value.status_code == status
    assert caught.value.problem == problem
    assert caught.value.request_id == "withdrawal-request"
    assert caught.value.retry_after == "9"
    assert len(calls) == 1


async def test_duplicate_error_keeps_caller_id_without_retry_or_lookup(asynchronous: bool) -> None:
    calls: list[httpx.Request] = []
    client_id = "000-client +/=?ю"
    body = _body(clientWithdrawalId=client_id)
    problem = {
        "type": "/api/problems/withdrawal_client_id_duplicate",
        "title": "Withdrawal already exists",
        "status": 400,
        "detail": "The specified client withdrawal ID is already in use",
        "kind": "client_data_validation",
        "instance": "/api/problems/instances/synthetic",
    }

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, json=problem)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(APIError) as caught:
            await _resolve(client.withdrawals.create(request=body))
    assert type(caught.value) is APIError
    assert caught.value.problem == problem
    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert json.loads(calls[0].content)["clientWithdrawalId"] == client_id
    assert body.client_withdrawal_id == client_id


@pytest.mark.parametrize(
    "failure", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout]
)
@pytest.mark.parametrize("length", [100, 150])
async def test_timeout_keeps_unknown_outcome_after_one_attempt_without_retry_or_lookup(
    asynchronous: bool, failure: type[httpx.TimeoutException], length: int
) -> None:
    calls: list[httpx.Request] = []
    client_id = "ю" * length
    body = _body(clientWithdrawalId=client_id)

    def fail(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise failure("Synthetic uncertain result", request=request)

    async with _client(asynchronous, fail) as client:
        with pytest.raises(RequestTimeoutError):
            await _resolve(client.withdrawals.create(request=body))
        assert len(calls) == 1
    assert calls[0].method == "POST"
    assert calls[0].url.path == "/api/v1/withdrawals"
    assert json.loads(calls[0].content)["clientWithdrawalId"] == client_id
    assert body.client_withdrawal_id == client_id


async def test_only_explicit_caller_lookup_uses_saved_short_id_after_unknown_timeout(
    asynchronous: bool,
) -> None:
    calls: list[httpx.Request] = []
    client_id = "000-client +/=?ю"

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            raise httpx.ReadTimeout("Synthetic unknown result", request=request)
        return httpx.Response(200, json=WITHDRAWAL)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(RequestTimeoutError):
            await _resolve(client.withdrawals.create(request=_body(clientWithdrawalId=client_id)))
        assert len(calls) == 1
        result = await _resolve(client.withdrawals.retrieve(client_withdrawal_id=client_id))

    assert len(calls) == 2
    assert [request.method for request in calls] == ["POST", "GET"]
    assert calls[1].url.path == "/api/v1/withdrawal"
    assert dict(calls[1].url.params) == {"clientWithdrawalId": client_id}
    assert result.withdrawal_id == WITHDRAWAL["withdrawalId"]


async def test_create_does_not_follow_redirects(asynchronous: bool) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(307, headers={"location": "https://other.invalid/sink"})

    async with _client(asynchronous, respond, follow_redirects=True) as client:
        with pytest.raises(APIError) as caught:
            await _resolve(client.withdrawals.create(request=_body()))
    assert caught.value.status_code == 307
    assert len(calls) == 1


async def test_shared_http_client_keeps_auth_defaults_and_caller_ownership(
    asynchronous: bool,
) -> None:
    calls: list[httpx.Request] = []
    auth = httpx.BasicAuth("unrelated", "synthetic-password")
    http_cls = httpx.AsyncClient if asynchronous else httpx.Client
    client_cls = AsyncPayClient if asynchronous else PayClient

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=WITHDRAWAL)

    http = http_cls(
        transport=httpx.MockTransport(respond),
        auth=auth,
        headers={"Authorization": "Bearer unrelated-token", "X-Custom": "retained"},
        timeout=77,
        base_url="https://unrelated.invalid",
        follow_redirects=True,
    )
    original_headers = dict(http.headers)
    original_timeout = http.timeout
    original_base_url = http.base_url
    clients = [
        client_cls(api_token=token, environment="testnet", timeout=12, http_client=http)
        for token in ("synthetic-first-token", "synthetic-second-token", None)
    ]
    try:
        for client in clients[:2]:
            await _resolve(client.withdrawals.create(request=_body()))
        with pytest.raises(AuthenticationError):
            await _resolve(clients[2].withdrawals.create(request=_body()))
        for client in clients:
            await _resolve(client.aclose() if asynchronous else client.close())
        assert not http.is_closed
        assert dict(http.headers) == original_headers
        assert http.timeout == original_timeout
        assert http.base_url == original_base_url
        assert http.follow_redirects is True
        assert http.auth is auth
    finally:
        await _resolve(http.aclose() if asynchronous else http.close())

    assert len(calls) == 2
    assert [r.headers["authorization"] for r in calls] == [
        "Bearer synthetic-first-token",
        "Bearer synthetic-second-token",
    ]
    for request in calls:
        assert request.url.host == "pay.api.testnet.xrocket.exchange"
        assert request.headers["x-custom"] == "retained"
        assert request.extensions["timeout"] == {"connect": 12, "read": 12, "write": 12, "pool": 12}


def test_public_request_exports_and_create_signatures_are_symmetric() -> None:
    for name in ("WithdrawalCreateRequest", "WithdrawalCallbackRequest"):
        assert name in pay.__all__
        assert name in models.__all__
        assert getattr(pay, name) is getattr(models, name)
        assert issubclass(getattr(pay, name), RequestModel)
    assert not issubclass(Withdrawal, RequestModel)
    assert not issubclass(WithdrawalCallback, RequestModel)
    sync = inspect.signature(WithdrawalsResource.create)
    asynchronous = inspect.signature(AsyncWithdrawalsResource.create)
    assert sync == asynchronous
    assert set(sync.parameters) == {"self", "request"}
    assert sync.parameters["request"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sync.parameters["request"].default is inspect.Parameter.empty
    assert not inspect.iscoroutinefunction(WithdrawalsResource.create)
    assert inspect.iscoroutinefunction(AsyncWithdrawalsResource.create)


def test_request_fields_and_create_policy_match_saved_current_oas() -> None:
    snapshot = json.loads(
        (Path(__file__).parents[1] / "spec" / "openapi" / "pay-current.json").read_text(
            encoding="utf-8"
        )
    )
    schemas = snapshot["components"]["schemas"]
    for model, schema_name in (
        (WithdrawalCreateRequest, "WithdrawalCreateRequestDto"),
        (WithdrawalCallbackRequest, "WithdrawalCallbackRequestDto"),
    ):
        assert {field.alias for field in model.model_fields.values()} == set(
            schemas[schema_name]["properties"]
        )
    schema = schemas["WithdrawalCreateRequestDto"]
    assert set(schema["required"]) == set(REQUIRED)
    assert all(
        WithdrawalCreateRequest.model_fields[name].is_required()
        for name in ("client_withdrawal_id", "network", "address", "asset", "amount")
    )
    assert schema["properties"]["network"]["default"] == "TON"
    assert schema["properties"]["clientWithdrawalId"]["maxLength"] == 150
    assert "minLength" not in schema["properties"]["clientWithdrawalId"]
    assert "maxLength" not in schema["properties"]["asset"]
    assert "required" not in schemas["WithdrawalCallbackRequestDto"]
    operation = snapshot["paths"]["/api/v1/withdrawals"]["post"]
    assert operation["parameters"] == []
    assert {status for status in operation["responses"] if status.startswith("2")} == {"200"}
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/WithdrawalCreateRequestDto"
    )
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/WithdrawalResponseDto"
    )
