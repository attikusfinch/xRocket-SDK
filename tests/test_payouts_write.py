"""Offline contracts for creating one Current Pay payout without hidden retries."""

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
    Payout,
    PayoutCallback,
    PayoutCallbackRequest,
    PayoutCreateRequest,
)
from xrocket.pay.resources.payouts import AsyncPayoutsResource, PayoutsResource

EXACT_AMOUNT = "12345678901234567890.1234567890123456789000"
REQUIRED = {
    "target": "000123",
    "targetType": "telegram_user_id",
    "asset": "USDT",
    "amount": "1.2300",
}
PAYOUT = {
    "payoutId": "synthetic-payout",
    "target": "000123",
    "targetType": "future_target",
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
    token: str | None = "synthetic-payout-token",
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


def _body(**changes: Any) -> PayoutCreateRequest:
    return PayoutCreateRequest.model_validate({**REQUIRED, **changes})


@pytest.mark.parametrize("all_fields", [False, True], ids=["minimal", "all-fields"])
async def test_create_sends_one_post_with_exact_money_and_returns_open_response(
    asynchronous: bool, all_fields: bool
) -> None:
    changes = (
        {
            "amount": Decimal(EXACT_AMOUNT),
            "client_payout_id": "000-client +/= &?%#ю",
            "description": "Заказ 東京 🎁",
            "callback": PayoutCallbackRequest(
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
        **PAYOUT,
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
        result = await _resolve(client.payouts.create(request=body))

    assert len(calls) == 1
    request = calls[0]
    assert request.method == "POST"
    assert str(request.url) == "https://pay.api.testnet.xrocket.exchange/api/v1/payouts"
    assert request.headers["authorization"] == "Bearer synthetic-payout-token"
    assert request.headers["accept"] == "application/json"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["content-length"] == str(len(request.content))
    assert "idempotency-key" not in request.headers
    assert "Rocket-Pay-Key" not in request.headers
    expected = dict(REQUIRED)
    if all_fields:
        expected.update(
            amount=EXACT_AMOUNT,
            clientPayoutId="000-client +/= &?%#ю",
            description="Заказ 東京 🎁",
            callback={
                "callbackUrl": "https://example.invalid/callback",
                "payload": {"custom": [None, True, "1E-19"]},
            },
        )
        assert "Заказ 東京 🎁".encode() in request.content
    assert json.loads(request.content) == expected
    assert body.model_fields_set == fields_set
    assert body.amount.as_tuple() == Decimal(expected["amount"]).as_tuple()
    assert isinstance(result, Payout)
    assert result.payout_id == "synthetic-payout"
    assert result.amount.as_tuple() == Decimal(EXACT_AMOUNT).as_tuple()
    assert result.target_type == "future_target"
    assert result.status == "future_status"
    assert result.model_extra == {"futureResponseField": {"retained": True}}
    assert isinstance(result.callback, PayoutCallback)
    assert result.callback.model_extra == {"futureCallbackField": 2}
    assert result.callback.payload == {"synthetic": True}


@pytest.mark.parametrize("target_type", ["user_id", "telegram_user_id", "telegram_username"])
def test_request_enum_accepts_all_documented_targets_and_preserves_empty_strings(
    target_type: str,
) -> None:
    payload = {
        "target": "",
        "targetType": target_type,
        "asset": "",
        "amount": "-0.0000",
        "clientPayoutId": "",
        "description": "",
        "callback": {"callbackUrl": "", "payload": {}},
    }
    assert json.loads(serialize_request(PayoutCreateRequest.model_validate(payload))) == payload


@pytest.mark.parametrize("callback", [{}, {"callbackUrl": ""}, {"payload": {}}])
def test_callback_properties_are_independently_optional(callback: dict[str, Any]) -> None:
    assert json.loads(serialize_request(_body(callback=callback))) == {
        **REQUIRED,
        "callback": callback,
    }


def test_snake_and_camel_input_aliases_have_identical_wire_output() -> None:
    snake = PayoutCreateRequest(
        target="000123",
        target_type="telegram_user_id",
        asset="USDT",
        amount="1.2300",
        client_payout_id="saved-client",
        description="Synthetic",
        callback=PayoutCallbackRequest(callback_url="https://example.invalid/callback", payload={}),
    )
    camel = PayoutCreateRequest.model_validate(
        {
            **REQUIRED,
            "clientPayoutId": "saved-client",
            "description": "Synthetic",
            "callback": {"callbackUrl": "https://example.invalid/callback", "payload": {}},
        }
    )
    assert json.loads(serialize_request(snake)) == json.loads(serialize_request(camel))


@pytest.mark.parametrize("field", ["target", "targetType", "asset", "amount"])
def test_create_requires_every_documented_required_field(field: str) -> None:
    payload = dict(REQUIRED)
    del payload[field]
    with pytest.raises(ValidationError):
        PayoutCreateRequest.model_validate(payload)


@pytest.mark.parametrize(
    "amount",
    [Decimal(EXACT_AMOUNT), "1E-40", Decimal("-0.0000"), "0", "-1.0000000000000000001"],
)
def test_amount_keeps_decimal_precision_without_invented_bounds(amount: str | Decimal) -> None:
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
        {"target": 123},
        {"targetType": 123},
        {"targetType": "future_target"},
        {"asset": 123},
        {"clientPayoutId": 123},
        {"description": 123},
        {"callback": []},
        {"callback": {"callbackUrl": 123}},
        {"callback": {"payload": []}},
        {"futureResponseField": True},
        {"callback": {"futureResponseField": True}},
    ],
)
def test_requests_are_strict_and_forbid_response_extras(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _body(**changes)


@pytest.mark.parametrize(
    "model,field,maximum",
    [
        (PayoutCreateRequest, "target", 100),
        (PayoutCreateRequest, "clientPayoutId", 50),
        (PayoutCallbackRequest, "callbackUrl", 500),
    ],
)
def test_string_length_limits_match_request_schema(model: Any, field: str, maximum: int) -> None:
    required = REQUIRED if model is PayoutCreateRequest else {}
    valid = model.model_validate({**required, field: "ю" * maximum})
    assert json.loads(serialize_request(valid))[field] == "ю" * maximum
    with pytest.raises(ValidationError):
        model.model_validate({**required, field: "ю" * (maximum + 1)})


def test_asset_and_description_do_not_borrow_limits_from_other_resources() -> None:
    body = _body(asset="x" * 1001, description="ю" * 10001)
    wire = json.loads(serialize_request(body))
    assert wire["asset"] == "x" * 1001
    assert wire["description"] == "ю" * 10001


@pytest.mark.parametrize(
    "model,field",
    [
        (PayoutCreateRequest, "clientPayoutId"),
        (PayoutCreateRequest, "description"),
        (PayoutCreateRequest, "callback"),
        (PayoutCallbackRequest, "callbackUrl"),
        (PayoutCallbackRequest, "payload"),
    ],
)
def test_optional_properties_allow_omission_and_reject_explicit_null(
    model: Any, field: str
) -> None:
    required = REQUIRED if model is PayoutCreateRequest else {}
    assert json.loads(serialize_request(model.model_validate(required))) == required
    with pytest.raises(ValidationError):
        model.model_validate({**required, field: None})


@pytest.mark.parametrize("kind", ["mapping", "response", "wrong_request", "null"])
async def test_create_requires_specific_request_dto_before_io(
    asynchronous: bool, kind: str
) -> None:
    bodies = {
        "mapping": REQUIRED,
        "response": Payout.model_validate(PAYOUT),
        "wrong_request": PayoutCallbackRequest(),
        "null": None,
    }

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("A non-payout request DTO reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(TypeError):
            await _resolve(client.payouts.create(request=bodies[kind]))


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", 0.1),
        ("target", "x" * 101),
        ("target_type", "future_target"),
        ("client_payout_id", "x" * 51),
        ("description", None),
    ],
)
@pytest.mark.parametrize("constructed", [False, True], ids=["mutated", "constructed"])
async def test_bypassed_validation_is_rechecked_before_io(
    asynchronous: bool, field: str, value: Any, constructed: bool
) -> None:
    if constructed:
        body = PayoutCreateRequest.model_construct(
            **{
                "target": "000123",
                "target_type": "user_id",
                "asset": "USDT",
                "amount": Decimal("1"),
                field: value,
            }
        )
    else:
        body = _body()
        setattr(body, field, value)

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An invalid mutated or constructed payout reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.payouts.create(request=body))


async def test_constructed_missing_required_field_is_revalidated_before_io(
    asynchronous: bool,
) -> None:
    body = PayoutCreateRequest.model_construct(target="000123", target_type="user_id", asset="USDT")

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("A constructed payout missing its amount reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.payouts.create(request=body))


async def test_nested_validation_and_model_boundaries_are_rechecked(asynchronous: bool) -> None:
    callback = PayoutCallbackRequest()
    body = _body(callback=callback)
    assert body.callback is not None
    body.callback.callback_url = "x" * 501

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An invalid nested payout request reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.payouts.create(request=body))
        body.callback = PayoutCallbackRequest(payload={"response": Payout.model_validate(PAYOUT)})
        with pytest.raises(TypeError):
            await _resolve(client.payouts.create(request=body))


async def test_create_requires_sdk_auth_before_io(asynchronous: bool) -> None:
    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An unauthenticated payout reached the network")

    async with _client(asynchronous, unexpected, token=None) as client:
        with pytest.raises(AuthenticationError):
            await _resolve(client.payouts.create(request=_body()))


@pytest.mark.parametrize("status", [201, 202, 204])
async def test_create_accepts_only_documented_200(asynchronous: bool, status: int) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(status, json=PAYOUT)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.payouts.create(request=_body()))


@pytest.mark.parametrize("content", [b"", b"null", b"{}", b"[]", b"not json"])
async def test_create_requires_a_valid_payout_response(asynchronous: bool, content: bytes) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(200, content=content)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.payouts.create(request=_body()))


@pytest.mark.parametrize(
    "changes", [{"amount": 0.1}, {"amount": "NaN"}, {"callback": {"payload": []}}]
)
async def test_create_malformed_response_fields_use_shared_error(
    asynchronous: bool, changes: dict[str, Any]
) -> None:
    async with _client(
        asynchronous, lambda _: httpx.Response(200, json={**PAYOUT, **changes})
    ) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.payouts.create(request=_body()))


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
            status, json=problem, headers={"x-request-id": "payout-request", "retry-after": "9"}
        )

    async with _client(asynchronous, respond) as client:
        with pytest.raises(error) as caught:
            await _resolve(client.payouts.create(request=_body()))
    assert type(caught.value) is error
    assert caught.value.status_code == status
    assert caught.value.problem == problem
    assert caught.value.request_id == "payout-request"
    assert caught.value.retry_after == "9"
    assert len(calls) == 1


async def test_duplicate_error_keeps_caller_id_and_does_not_retry_or_lookup(
    asynchronous: bool,
) -> None:
    calls: list[httpx.Request] = []
    body = _body(client_payout_id="000-client +/=?ю")
    problem = {
        "type": "/api/problems/payout_client_id_duplicate",
        "title": "Payout already exists",
        "status": 400,
        "detail": "The specified client payout ID is already in use",
        "kind": "client_data_validation",
        "instance": "/api/problems/instances/synthetic",
    }

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, json=problem)

    async with _client(asynchronous, respond) as client:
        with pytest.raises(APIError) as caught:
            await _resolve(client.payouts.create(request=body))
    assert type(caught.value) is APIError
    assert caught.value.problem == problem
    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert json.loads(calls[0].content)["clientPayoutId"] == "000-client +/=?ю"
    assert body.client_payout_id == "000-client +/=?ю"


@pytest.mark.parametrize(
    "failure", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout]
)
async def test_timeout_makes_one_attempt_without_retry_or_automatic_lookup(
    asynchronous: bool, failure: type[httpx.TimeoutException]
) -> None:
    calls: list[httpx.Request] = []
    body = _body(client_payout_id="saved-before-send")

    def fail(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise failure("Synthetic uncertain result", request=request)

    async with _client(asynchronous, fail) as client:
        with pytest.raises(RequestTimeoutError):
            await _resolve(client.payouts.create(request=body))
        assert len(calls) == 1
    assert calls[0].method == "POST"
    assert calls[0].url.path == "/api/v1/payouts"
    assert json.loads(calls[0].content)["clientPayoutId"] == "saved-before-send"
    assert body.client_payout_id == "saved-before-send"


async def test_caller_can_explicitly_lookup_saved_client_id_after_unknown_timeout(
    asynchronous: bool,
) -> None:
    calls: list[httpx.Request] = []
    client_id = "000-client +/=?ю"
    body = _body(client_payout_id=client_id)

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            raise httpx.ReadTimeout("Synthetic unknown result", request=request)
        return httpx.Response(200, json={**PAYOUT, "clientPayoutId": client_id})

    async with _client(asynchronous, respond) as client:
        with pytest.raises(RequestTimeoutError):
            await _resolve(client.payouts.create(request=body))
        assert len(calls) == 1
        result = await _resolve(client.payouts.retrieve(client_payout_id=client_id))

    assert len(calls) == 2
    assert [request.method for request in calls] == ["POST", "GET"]
    assert calls[1].url.path == "/api/v1/payout"
    assert dict(calls[1].url.params) == {"clientPayoutId": client_id}
    assert result.client_payout_id == client_id


async def test_create_does_not_follow_redirects(asynchronous: bool) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(307, headers={"location": "https://other.invalid/sink"})

    async with _client(asynchronous, respond, follow_redirects=True) as client:
        with pytest.raises(APIError) as caught:
            await _resolve(client.payouts.create(request=_body()))
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
        return httpx.Response(200, json=PAYOUT)

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
            await _resolve(client.payouts.create(request=_body()))
        with pytest.raises(AuthenticationError):
            await _resolve(clients[2].payouts.create(request=_body()))
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
    for name in ("PayoutCreateRequest", "PayoutCallbackRequest"):
        assert name in pay.__all__
        assert name in models.__all__
        assert getattr(pay, name) is getattr(models, name)
        assert issubclass(getattr(pay, name), RequestModel)
    assert not issubclass(Payout, RequestModel)
    assert not issubclass(PayoutCallback, RequestModel)
    sync = inspect.signature(PayoutsResource.create)
    asynchronous = inspect.signature(AsyncPayoutsResource.create)
    assert sync == asynchronous
    assert set(sync.parameters) == {"self", "request"}
    assert sync.parameters["request"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sync.parameters["request"].default is inspect.Parameter.empty
    assert not inspect.iscoroutinefunction(PayoutsResource.create)
    assert inspect.iscoroutinefunction(AsyncPayoutsResource.create)


def test_request_fields_and_create_policy_match_saved_current_oas() -> None:
    snapshot = json.loads(
        (Path(__file__).parents[1] / "spec" / "openapi" / "pay-current.json").read_text(
            encoding="utf-8"
        )
    )
    schemas = snapshot["components"]["schemas"]
    for model, schema_name in (
        (PayoutCreateRequest, "AppPayoutCreateRequestDto"),
        (PayoutCallbackRequest, "PayoutCallbackRequestDto"),
    ):
        assert {field.alias for field in model.model_fields.values()} == set(
            schemas[schema_name]["properties"]
        )
    assert set(schemas["AppPayoutCreateRequestDto"]["required"]) == set(REQUIRED)
    assert "required" not in schemas["PayoutCallbackRequestDto"]
    assert "maxLength" not in schemas["AppPayoutCreateRequestDto"]["properties"]["description"]
    operation = snapshot["paths"]["/api/v1/payouts"]["post"]
    assert operation["parameters"] == []
    assert {status for status in operation["responses"] if status.startswith("2")} == {"200"}
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/AppPayoutCreateRequestDto"
    )
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/AppPayoutResponseDto"
    )
