"""Offline contracts for one batch attempt and explicit per-item payout results."""

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
    MassPayoutCreateRequest,
    MassPayoutError,
    MassPayoutErrorReason,
    MassPayoutItemRequest,
    MassPayoutResult,
    PayClient,
    Payout,
    PayoutCallbackRequest,
    PayoutCreateRequest,
)
from xrocket.pay.resources.payouts import AsyncPayoutsResource, PayoutsResource

EXACT_AMOUNT = "12345678901234567890.1234567890123456789000"
ITEM = {"target": "000123", "targetType": "telegram_user_id", "amount": "1.2300"}
REQUIRED = {"asset": "USDT", "payouts": [ITEM]}
PAYOUT = {
    "payoutId": "synthetic-payout",
    "target": "000123",
    "targetType": "future_target",
    "asset": "USDT",
    "amount": EXACT_AMOUNT,
    "status": "future_status",
}
REASON = {
    "type": "/api/problems/future_item_failure",
    "title": "Synthetic failure",
    "status": 400,
    "detail": "Synthetic item was rejected",
    "instance": "/api/problems/instances/synthetic",
    "kind": "future_kind",
}
ERROR = {
    "target": "000123",
    "targetType": "future_target",
    "amount": EXACT_AMOUNT,
    "reason": REASON,
}
EMPTY_RESULT = {"successPayouts": [], "errorPayouts": []}
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
    token: str | None = "synthetic-mass-payout-token",
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


def _item(**changes: Any) -> MassPayoutItemRequest:
    return MassPayoutItemRequest.model_validate({**ITEM, **changes})


def _body(**changes: Any) -> MassPayoutCreateRequest:
    return MassPayoutCreateRequest.model_validate({**REQUIRED, **changes})


@pytest.mark.parametrize("all_fields", [False, True], ids=["minimal", "all-fields"])
async def test_create_mass_sends_exact_batch_body_once(
    asynchronous: bool, all_fields: bool
) -> None:
    item = _item(
        **(
            {
                "amount": Decimal(EXACT_AMOUNT),
                "clientPayoutId": "000-client +/= &?%#ю",
                "description": "Заказ 東京 🎁",
                "callback": PayoutCallbackRequest(
                    callback_url="https://example.invalid/callback",
                    payload={"custom": [None, True, Decimal("0.0000000000000000001")]},
                ),
            }
            if all_fields
            else {}
        )
    )
    body = MassPayoutCreateRequest(asset="USDT", payouts=[item])
    fields_set = body.model_fields_set.copy()
    item_fields_set = body.payouts[0].model_fields_set.copy()
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"successPayouts": [PAYOUT], "errorPayouts": []})

    async with _client(asynchronous, respond) as client:
        result = await _resolve(client.payouts.create_mass(request=body))

    assert len(calls) == 1
    request = calls[0]
    assert request.method == "POST"
    assert str(request.url) == "https://pay.api.testnet.xrocket.exchange/api/v1/mass-payouts"
    assert request.headers["authorization"] == "Bearer synthetic-mass-payout-token"
    assert request.headers["accept"] == "application/json"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["content-length"] == str(len(request.content))
    assert "idempotency-key" not in request.headers
    assert "Rocket-Pay-Key" not in request.headers
    expected_item = dict(ITEM)
    if all_fields:
        expected_item.update(
            amount=EXACT_AMOUNT,
            clientPayoutId="000-client +/= &?%#ю",
            description="Заказ 東京 🎁",
            callback={
                "callbackUrl": "https://example.invalid/callback",
                "payload": {"custom": [None, True, "1E-19"]},
            },
        )
        assert "Заказ 東京 🎁".encode() in request.content
    assert json.loads(request.content) == {"asset": "USDT", "payouts": [expected_item]}
    assert body.model_fields_set == fields_set
    assert body.payouts[0].model_fields_set == item_fields_set
    assert body.payouts[0].amount.as_tuple() == Decimal(expected_item["amount"]).as_tuple()
    assert isinstance(result, MassPayoutResult)
    assert isinstance(result.success_payouts[0], Payout)
    assert result.success_payouts[0].amount.as_tuple() == Decimal(EXACT_AMOUNT).as_tuple()


@pytest.mark.parametrize("outcome", ["mixed", "all-success", "all-error"])
async def test_results_keep_reordered_original_item_ids_and_explicit_failures(
    asynchronous: bool, outcome: str
) -> None:
    ids = ["000-first +/=?ю", "000-second +/=?ю", "000-third +/=?ю"]
    body = _body(
        payouts=[
            _item(client_payout_id=client_id, amount=str(index + 1))
            for index, client_id in enumerate(ids)
        ]
    )
    indexes = {
        "mixed": ([2, 0], [1]),
        "all-success": ([2, 0, 1], []),
        "all-error": ([], [2, 0, 1]),
    }
    success_indexes, error_indexes = indexes[outcome]
    response = {
        "successPayouts": [
            {**PAYOUT, "payoutId": f"server-{i}", "clientPayoutId": ids[i], "amount": str(i + 1)}
            for i in success_indexes
        ],
        "errorPayouts": [
            {**ERROR, "clientPayoutId": ids[i], "amount": str(i + 1)} for i in error_indexes
        ],
        "futureBatchField": {"retained": True},
    }
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=response)

    async with _client(asynchronous, respond) as client:
        result = await _resolve(client.payouts.create_mass(request=body))

    assert len(calls) == 1
    assert [item.client_payout_id for item in result.success_payouts] == [
        ids[i] for i in success_indexes
    ]
    assert [item.payout_id for item in result.success_payouts] == [
        f"server-{i}" for i in success_indexes
    ]
    assert [item.client_payout_id for item in result.error_payouts] == [
        ids[i] for i in error_indexes
    ]
    assert all(isinstance(item, Payout) for item in result.success_payouts)
    assert all(isinstance(item, MassPayoutError) for item in result.error_payouts)
    assert all(isinstance(item.reason, MassPayoutErrorReason) for item in result.error_payouts)
    assert result.has_errors is bool(error_indexes)
    assert result.is_partial is (outcome == "mixed")
    assert "success" not in type(result).model_fields
    assert "success" not in result.model_dump()
    assert result.model_extra == {"futureBatchField": {"retained": True}}
    assert [item.client_payout_id for item in body.payouts] == ids
    assert [item["clientPayoutId"] for item in json.loads(calls[0].content)["payouts"]] == ids
    assert all(request.method == "POST" for request in calls)


async def test_duplicate_result_items_are_retained_without_inventing_correlation(
    asynchronous: bool,
) -> None:
    ids = ["saved-first", "saved-second"]
    body = _body(payouts=[_item(client_payout_id=client_id) for client_id in ids])
    success = {**PAYOUT, "targetType": "telegram_user_id"}
    error = {**ERROR, "targetType": "telegram_user_id"}
    response = {"successPayouts": [success, success], "errorPayouts": [error, error]}
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=response)

    async with _client(asynchronous, respond) as client:
        result = await _resolve(client.payouts.create_mass(request=body))

    assert len(calls) == 1
    assert len(result.success_payouts) == 2
    assert len(result.error_payouts) == 2
    assert result.success_payouts[0] == result.success_payouts[1]
    assert result.error_payouts[0] == result.error_payouts[1]
    assert [item.payout_id for item in result.success_payouts] == ["synthetic-payout"] * 2
    for item in [*result.success_payouts, *result.error_payouts]:
        assert item.target == "000123"
        assert item.client_payout_id is None
        assert "client_payout_id" not in item.model_fields_set
        assert "clientPayoutId" not in item.model_dump(by_alias=True, exclude_unset=True)
    assert [item.client_payout_id for item in body.payouts] == ids
    assert [item["clientPayoutId"] for item in json.loads(calls[0].content)["payouts"]] == ids
    assert result.has_errors is True
    assert result.is_partial is True


async def test_open_typed_item_error_keeps_money_reason_and_correlation(asynchronous: bool) -> None:
    response = {
        "successPayouts": [],
        "errorPayouts": [
            {
                **ERROR,
                "clientPayoutId": "000-preserved",
                "description": "Synthetic original description",
                "futureItemField": [1, 2],
                "reason": {**REASON, "status": 400.5, "futureReasonField": {"retained": True}},
            }
        ],
    }
    async with _client(asynchronous, lambda _: httpx.Response(200, json=response)) as client:
        result = await _resolve(client.payouts.create_mass(request=_body()))

    item = result.error_payouts[0]
    assert item.target == "000123"
    assert item.target_type == "future_target"
    assert item.amount.as_tuple() == Decimal(EXACT_AMOUNT).as_tuple()
    assert item.client_payout_id == "000-preserved"
    assert item.description == "Synthetic original description"
    assert item.model_extra == {"futureItemField": [1, 2]}
    assert item.reason.type == "/api/problems/future_item_failure"
    assert item.reason.kind == "future_kind"
    assert item.reason.status == 400.5
    assert type(item.reason.status) is float
    assert item.reason.model_extra == {"futureReasonField": {"retained": True}}
    assert result.has_errors is True
    assert result.is_partial is False


@pytest.mark.parametrize("count", [0, 501])
async def test_no_inferred_batch_bounds_or_splitting(asynchronous: bool, count: int) -> None:
    # This proves only local wire policy; it makes no claim about server acceptance.
    body = _body(payouts=[_item(client_payout_id=f"saved-{i}") for i in range(count)])
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=EMPTY_RESULT)

    async with _client(asynchronous, respond) as client:
        result = await _resolve(client.payouts.create_mass(request=body))

    assert len(calls) == 1
    assert calls[0].url.path == "/api/v1/mass-payouts"
    assert len(json.loads(calls[0].content)["payouts"]) == count
    assert result.has_errors is False
    assert result.is_partial is False


def test_snake_and_camel_aliases_have_identical_wire_output_and_optional_omission() -> None:
    snake = MassPayoutCreateRequest(
        asset="USDT",
        payouts=[
            MassPayoutItemRequest(
                target="000123",
                target_type="telegram_user_id",
                amount="1.2300",
                client_payout_id="saved-client",
                callback=PayoutCallbackRequest(callback_url="", payload={}),
            )
        ],
    )
    camel = _body(
        payouts=[
            {
                **ITEM,
                "clientPayoutId": "saved-client",
                "callback": {"callbackUrl": "", "payload": {}},
            }
        ]
    )
    assert json.loads(serialize_request(snake)) == json.loads(serialize_request(camel))
    assert json.loads(serialize_request(_body())) == REQUIRED
    assert json.loads(
        serialize_request(_body(asset="", payouts=[_item(target="", amount="-0.0000")]))
    ) == {
        "asset": "",
        "payouts": [{"target": "", "targetType": "telegram_user_id", "amount": "-0.0000"}],
    }


@pytest.mark.parametrize(
    "target_type", ["user_id", "telegram_username", "future_target", "TelegramUserId"]
)
def test_batch_target_policy_follows_telegram_user_id_prose(target_type: str) -> None:
    with pytest.raises(ValidationError):
        _item(targetType=target_type)


@pytest.mark.parametrize("field", ["asset", "payouts"])
def test_enclosing_request_requires_documented_fields(field: str) -> None:
    payload = dict(REQUIRED)
    del payload[field]
    with pytest.raises(ValidationError):
        MassPayoutCreateRequest.model_validate(payload)


@pytest.mark.parametrize("field", ["target", "targetType", "amount"])
def test_items_require_documented_fields(field: str) -> None:
    item = dict(ITEM)
    del item[field]
    with pytest.raises(ValidationError):
        _body(payouts=[item])


@pytest.mark.parametrize(
    "amount", [Decimal(EXACT_AMOUNT), "1E-40", Decimal("-0.0000"), "0", "-1.0000000000000000001"]
)
def test_item_money_preserves_exact_decimal_without_invented_bounds(amount: str | Decimal) -> None:
    body = _body(payouts=[_item(amount=amount)])
    assert body.payouts[0].amount.as_tuple() == Decimal(amount).as_tuple()
    assert json.loads(serialize_request(body))["payouts"][0]["amount"] == str(Decimal(amount))


@pytest.mark.parametrize(
    "amount", [0, 0.1, True, None, b"1", "", "invalid", "NaN", "Infinity", Decimal("NaN")]
)
def test_item_money_rejects_lossy_coercion_and_non_finite_values(amount: Any) -> None:
    with pytest.raises(ValidationError):
        _body(payouts=[{**ITEM, "amount": amount}])


@pytest.mark.parametrize(
    "changes",
    [
        {"asset": 123},
        {"payouts": ()},
        {"payouts": {}},
        {"payouts": [None]},
        {"payouts": [{**ITEM, "target": 123}]},
        {"payouts": [{**ITEM, "targetType": 123}]},
        {"payouts": [{**ITEM, "clientPayoutId": 123}]},
        {"payouts": [{**ITEM, "description": 123}]},
        {"payouts": [{**ITEM, "callback": []}]},
        {"payouts": [{**ITEM, "callback": {"payload": []}}]},
        {"payouts": [{**ITEM, "asset": "USDT"}]},
        {"payouts": [{**ITEM, "future": True}]},
        {"future": True},
    ],
)
def test_batch_requests_are_strict_and_forbid_extras(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _body(**changes)


@pytest.mark.parametrize("field", ["clientPayoutId", "description", "callback"])
def test_optional_item_fields_reject_explicit_null(field: str) -> None:
    with pytest.raises(ValidationError):
        _body(payouts=[{**ITEM, field: None}])


@pytest.mark.parametrize("field,maximum", [("target", 100), ("clientPayoutId", 50)])
def test_item_string_limits_are_schema_lengths(field: str, maximum: int) -> None:
    body = _body(payouts=[{**ITEM, field: "ю" * maximum}])
    assert json.loads(serialize_request(body))["payouts"][0][field] == "ю" * maximum
    with pytest.raises(ValidationError):
        _body(payouts=[{**ITEM, field: "ю" * (maximum + 1)}])


def test_no_borrowed_asset_or_description_limits() -> None:
    body = _body(asset="x" * 1001, payouts=[_item(description="ю" * 10001)])
    wire = json.loads(serialize_request(body))
    assert wire["asset"] == "x" * 1001
    assert wire["payouts"][0]["description"] == "ю" * 10001


@pytest.mark.parametrize("kind", ["mapping", "response", "single_request", "item_request", "null"])
async def test_create_mass_requires_specific_request_dto_before_io(
    asynchronous: bool, kind: str
) -> None:
    bodies = {
        "mapping": REQUIRED,
        "response": MassPayoutResult.model_validate(EMPTY_RESULT),
        "single_request": PayoutCreateRequest.model_validate({**ITEM, "asset": "USDT"}),
        "item_request": _item(),
        "null": None,
    }

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("A non-mass request DTO reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(TypeError):
            await _resolve(client.payouts.create_mass(request=bodies[kind]))


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", 0.1),
        ("target", "x" * 101),
        ("target_type", "user_id"),
        ("client_payout_id", "x" * 51),
        ("description", None),
    ],
)
@pytest.mark.parametrize("constructed", [False, True], ids=["mutated", "constructed"])
async def test_bypassed_nested_item_validation_is_rechecked_before_io(
    asynchronous: bool, field: str, value: Any, constructed: bool
) -> None:
    if constructed:
        item = MassPayoutItemRequest.model_construct(
            **{
                "target": "000123",
                "target_type": "telegram_user_id",
                "amount": Decimal("1"),
                field: value,
            }
        )
        body = MassPayoutCreateRequest.model_construct(asset="USDT", payouts=[item])
    else:
        body = _body()
        setattr(body.payouts[0], field, value)

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An invalid nested batch item reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.payouts.create_mass(request=body))


async def test_constructed_missing_fields_and_mutated_envelope_fail_before_io(
    asynchronous: bool,
) -> None:
    missing = MassPayoutCreateRequest.model_construct(
        asset="USDT",
        payouts=[
            MassPayoutItemRequest.model_construct(target="000123", target_type="telegram_user_id")
        ],
    )
    mutated = _body()
    mutated.asset = None

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An invalid batch envelope or incomplete item reached the network")

    async with _client(asynchronous, unexpected) as client:
        for body in (missing, mutated):
            with pytest.raises(ValidationError):
                await _resolve(client.payouts.create_mass(request=body))


async def test_nested_callback_validation_and_response_boundaries_are_rechecked(
    asynchronous: bool,
) -> None:
    body = _body(payouts=[_item(callback=PayoutCallbackRequest())])
    callback = body.payouts[0].callback
    assert callback is not None
    callback.callback_url = "x" * 501

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An invalid callback or embedded response reached the network")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.payouts.create_mass(request=body))
        body.payouts[0].callback = PayoutCallbackRequest(
            payload={"response": Payout.model_validate(PAYOUT)}
        )
        with pytest.raises(TypeError):
            await _resolve(client.payouts.create_mass(request=body))


def test_constructed_empty_fields_set_does_not_drop_required_nested_wire_fields() -> None:
    item = MassPayoutItemRequest.model_construct(
        _fields_set=set(), target="000123", target_type="telegram_user_id", amount=Decimal("1.2300")
    )
    body = MassPayoutCreateRequest.model_construct(_fields_set=set(), asset="USDT", payouts=[item])
    assert json.loads(serialize_request(body)) == REQUIRED
    assert body.model_fields_set == set()
    assert item.model_fields_set == set()


@pytest.mark.parametrize("field", ["successPayouts", "errorPayouts"])
def test_both_result_collections_are_required_and_nonnullable(field: str) -> None:
    missing = dict(EMPTY_RESULT)
    del missing[field]
    for payload in (missing, {**EMPTY_RESULT, field: None}, {**EMPTY_RESULT, field: {}}):
        with pytest.raises(ValidationError):
            MassPayoutResult.model_validate(payload)


@pytest.mark.parametrize("field", ["target", "targetType", "amount", "reason"])
def test_item_error_requires_every_documented_field(field: str) -> None:
    payload = dict(ERROR)
    del payload[field]
    with pytest.raises(ValidationError):
        MassPayoutError.model_validate(payload)


@pytest.mark.parametrize("field", ["type", "title", "status", "detail", "instance", "kind"])
def test_reason_requires_every_documented_field(field: str) -> None:
    reason = dict(REASON)
    del reason[field]
    with pytest.raises(ValidationError):
        MassPayoutErrorReason.model_validate(reason)


@pytest.mark.parametrize("status", [400, 400.0, 400.5, -1, 0])
def test_reason_status_preserves_finite_oas_numbers(status: int | float) -> None:
    reason = MassPayoutErrorReason.model_validate({**REASON, "status": status})
    assert reason.status == status
    assert type(reason.status) is type(status)


@pytest.mark.parametrize(
    "status", ["400", True, False, None, float("nan"), float("inf"), Decimal("400")]
)
def test_reason_status_rejects_coercion_and_non_finite_values(status: Any) -> None:
    with pytest.raises(ValidationError):
        MassPayoutErrorReason.model_validate({**REASON, "status": status})


async def test_create_mass_requires_sdk_auth_before_io(asynchronous: bool) -> None:
    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An unauthenticated batch reached the network")

    async with _client(asynchronous, unexpected, token=None) as client:
        with pytest.raises(AuthenticationError):
            await _resolve(client.payouts.create_mass(request=_body()))


@pytest.mark.parametrize("status", [201, 202, 204])
async def test_create_mass_accepts_only_documented_200(asynchronous: bool, status: int) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(status, json=EMPTY_RESULT)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.payouts.create_mass(request=_body()))


@pytest.mark.parametrize(
    "content", [b"", b"null", b"{}", b"[]", b"not json", b'{"successPayouts":[]}']
)
async def test_create_mass_requires_valid_typed_result(asynchronous: bool, content: bytes) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(200, content=content)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.payouts.create_mass(request=_body()))


@pytest.mark.parametrize(
    "response",
    [
        {"successPayouts": [{**PAYOUT, "amount": 0.1}], "errorPayouts": []},
        {"successPayouts": [], "errorPayouts": [{**ERROR, "amount": "NaN"}]},
        {"successPayouts": [], "errorPayouts": [{**ERROR, "reason": {**REASON, "status": "400"}}]},
        {"successPayouts": [], "errorPayouts": [{**ERROR, "reason": None}]},
    ],
)
async def test_malformed_item_response_uses_shared_validation_error(
    asynchronous: bool, response: dict[str, Any]
) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(200, json=response)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.payouts.create_mass(request=_body()))


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
    problem = {**REASON, "status": status, "future": {"retained": True}}

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status, json=problem, headers={"x-request-id": "batch-request", "retry-after": "9"}
        )

    async with _client(asynchronous, respond) as client:
        with pytest.raises(error) as caught:
            await _resolve(client.payouts.create_mass(request=_body()))
    assert type(caught.value) is error
    assert caught.value.status_code == status
    assert caught.value.problem == problem
    assert caught.value.request_id == "batch-request"
    assert caught.value.retry_after == "9"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "failure", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout]
)
async def test_timeout_makes_one_attempt_without_replay_or_lookup(
    asynchronous: bool, failure: type[httpx.TimeoutException]
) -> None:
    calls: list[httpx.Request] = []
    ids = ["saved-first", "saved-second"]
    body = _body(payouts=[_item(client_payout_id=client_id) for client_id in ids])

    def fail(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise failure("Synthetic unknown batch result", request=request)

    async with _client(asynchronous, fail) as client:
        with pytest.raises(RequestTimeoutError):
            await _resolve(client.payouts.create_mass(request=body))
    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert calls[0].url.path == "/api/v1/mass-payouts"
    assert [item["clientPayoutId"] for item in json.loads(calls[0].content)["payouts"]] == ids
    assert [item.client_payout_id for item in body.payouts] == ids


async def test_create_mass_does_not_follow_redirects(asynchronous: bool) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(307, headers={"location": "https://other.invalid/sink"})

    async with _client(asynchronous, respond, follow_redirects=True) as client:
        with pytest.raises(APIError) as caught:
            await _resolve(client.payouts.create_mass(request=_body()))
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
        return httpx.Response(200, json=EMPTY_RESULT)

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
            await _resolve(client.payouts.create_mass(request=_body()))
        with pytest.raises(AuthenticationError):
            await _resolve(clients[2].payouts.create_mass(request=_body()))
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


def test_public_exports_and_create_mass_signatures_are_symmetric() -> None:
    for name in (
        "MassPayoutCreateRequest",
        "MassPayoutItemRequest",
        "MassPayoutResult",
        "MassPayoutError",
        "MassPayoutErrorReason",
    ):
        assert name in pay.__all__
        assert name in models.__all__
        assert getattr(pay, name) is getattr(models, name)
    for model in (MassPayoutCreateRequest, MassPayoutItemRequest):
        assert issubclass(model, RequestModel)
    for model in (MassPayoutResult, MassPayoutError, MassPayoutErrorReason):
        assert not issubclass(model, RequestModel)
    sync = inspect.signature(PayoutsResource.create_mass)
    asynchronous = inspect.signature(AsyncPayoutsResource.create_mass)
    assert sync == asynchronous
    assert set(sync.parameters) == {"self", "request"}
    assert sync.parameters["request"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sync.parameters["request"].default is inspect.Parameter.empty
    assert not inspect.iscoroutinefunction(PayoutsResource.create_mass)
    assert inspect.iscoroutinefunction(AsyncPayoutsResource.create_mass)


def test_batch_fields_and_documented_policies_match_saved_current_oas() -> None:
    snapshot = json.loads(
        (Path(__file__).parents[1] / "spec" / "openapi" / "pay-current.json").read_text(
            encoding="utf-8"
        )
    )
    schemas = snapshot["components"]["schemas"]
    for model, schema_name in (
        (MassPayoutCreateRequest, "MassPayoutsCreateRequestDto"),
        (MassPayoutItemRequest, "MassPayoutsPayoutRequestDto"),
        (MassPayoutResult, "MassPayoutsCreateResponseDto"),
        (MassPayoutError, "MassPayoutsErrorResponseDto"),
        (MassPayoutErrorReason, "MassPayoutsReasonResponseDto"),
    ):
        schema = schemas[schema_name]
        assert {field.alias for field in model.model_fields.values()} == set(schema["properties"])
        assert {field.alias for field in model.model_fields.values() if field.is_required()} == set(
            schema["required"]
        )
    batch = schemas["MassPayoutsCreateRequestDto"]["properties"]["payouts"]
    assert "minItems" not in batch
    assert "maxItems" not in batch
    assert batch["items"]["maxLength"] == 500
    item = schemas["MassPayoutsPayoutRequestDto"]["properties"]
    assert item["targetType"]["enum"] == ["user_id", "telegram_user_id", "telegram_username"]
    assert "only TelegramUserId" in item["targetType"]["description"]
    assert item["target"]["maxLength"] == 100
    assert item["clientPayoutId"]["maxLength"] == 50
    assert "maxLength" not in item["description"]
    operation = snapshot["paths"]["/api/v1/mass-payouts"]["post"]
    assert operation["parameters"] == []
    assert {status for status in operation["responses"] if status.startswith("2")} == {"200"}
    assert (
        operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MassPayoutsCreateRequestDto"
    )
    assert (
        operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MassPayoutsCreateResponseDto"
    )
