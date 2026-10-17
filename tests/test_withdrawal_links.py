"""Offline Current link creation, separate from direct withdrawals and Legacy."""

import inspect
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
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
    RequestTimeoutError,
    ResponseValidationError,
    ServerError,
)
from xrocket._core.serialization import RequestModel, serialize_request
from xrocket.pay import (
    AsyncPayClient,
    PayClient,
    WithdrawalCreateRequest,
    WithdrawalLink,
    WithdrawalLinkRequest,
)
from xrocket.pay.resources.withdrawal_links import (
    AsyncWithdrawalLinksResource,
    WithdrawalLinksResource,
)

EXACT_AMOUNT = "12345678901234567890.1234567890123456789000"
REQUIRED = {"network": "TON", "address": "synthetic-address", "asset": "USDT", "amount": "1.2300"}
LINKS = {
    "telegramBotLink": "https://example.invalid/bot?start=synthetic",
    "telegramMiniAppLink": "https://example.invalid/mini-app",
    "webLink": "https://example.invalid/web",
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
    token: str | None = "synthetic-link-token",
    **http_options: Any,
) -> AsyncIterator[Any]:
    http_cls = httpx.AsyncClient if asynchronous else httpx.Client
    client_cls = AsyncPayClient if asynchronous else PayClient
    http = http_cls(transport=httpx.MockTransport(handler), **http_options)
    client = client_cls(api_token=token, http_client=http, environment="testnet", timeout=12)
    try:
        yield client
    finally:
        await _resolve(client.aclose() if asynchronous else client.close())
        assert not http.is_closed
        await _resolve(http.aclose() if asynchronous else http.close())


def _body(**changes: Any) -> WithdrawalLinkRequest:
    return WithdrawalLinkRequest.model_validate({**REQUIRED, **changes})


@pytest.mark.parametrize("all_fields", [False, True], ids=["minimal", "all-fields"])
async def test_exact_post_body_and_optional_links_without_followup_requests(
    asynchronous: bool, all_fields: bool
) -> None:
    body = (
        _body(
            network="ETH",
            address="  0xMiXeD 東京 🎁  ",
            asset=" usdt ",
            amount=Decimal(EXACT_AMOUNT),
            comment="  Заказ 🎁  ",
            platform="synthetic-platform",
        )
        if all_fields
        else _body()
    )
    fields_set = body.model_fields_set.copy()
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={**LINKS, "future": {"retained": True}})

    async with _client(asynchronous, respond) as client:
        result = await _resolve(client.withdrawal_links.create(request=body))

    assert len(calls) == 1
    request = calls[0]
    assert request.method == "POST"
    assert str(request.url) == "https://pay.api.testnet.xrocket.exchange/api/v1/withdrawal-link"
    assert request.headers["authorization"] == "Bearer synthetic-link-token"
    assert request.headers["accept"] == "application/json"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["content-length"] == str(len(request.content))
    assert "idempotency-key" not in request.headers
    assert "Rocket-Pay-Key" not in request.headers
    expected = dict(REQUIRED)
    if all_fields:
        expected.update(
            network="ETH",
            address="  0xMiXeD 東京 🎁  ",
            asset=" usdt ",
            amount=EXACT_AMOUNT,
            comment="  Заказ 🎁  ",
            platform="synthetic-platform",
        )
        assert "  Заказ 🎁  ".encode() in request.content
    assert json.loads(request.content) == expected
    assert body.model_fields_set == fields_set
    assert body.amount.as_tuple() == Decimal(expected["amount"]).as_tuple()
    assert isinstance(result, WithdrawalLink)
    assert result.telegram_bot_link == LINKS["telegramBotLink"]
    assert result.telegram_mini_app_link == LINKS["telegramMiniAppLink"]
    assert result.web_link == LINKS["webLink"]
    assert result.model_extra == {"future": {"retained": True}}


@pytest.mark.parametrize("links", [{}, *({key: value} for key, value in LINKS.items()), LINKS])
async def test_each_response_link_is_independently_optional(
    asynchronous: bool, links: dict[str, str]
) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(200, json=links)) as client:
        result = await _resolve(client.withdrawal_links.create(request=_body()))
    assert result.model_dump(by_alias=True, exclude_unset=True) == links
    for name, field in WithdrawalLink.model_fields.items():
        assert getattr(result, name) == links.get(field.alias)


@pytest.mark.parametrize("value", ["", "future-scheme:opaque?x=ю", "  unchanged plain text  "])
def test_links_are_plain_strings_without_url_validation_or_normalization(value: str) -> None:
    result = WithdrawalLink.model_validate({key: value for key in LINKS})
    assert result.model_dump(by_alias=True, exclude_unset=True) == dict.fromkeys(LINKS, value)


@pytest.mark.parametrize("field", list(LINKS))
@pytest.mark.parametrize("value", [None, 123, True, [], {}])
async def test_present_response_links_retain_non_nullable_string_contract(
    asynchronous: bool, field: str, value: Any
) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(200, json={field: value})) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.withdrawal_links.create(request=_body()))


@pytest.mark.parametrize("network", ["TON", "BSC", "ETH", "BTC", "TRX", "SOL"])
def test_all_networks_and_schema_allowed_empty_strings(network: str) -> None:
    payload = dict(network=network, address="", asset="", amount="-0.0000", comment="", platform="")
    assert json.loads(serialize_request(WithdrawalLinkRequest.model_validate(payload))) == payload


@pytest.mark.parametrize("field", list(REQUIRED))
def test_each_required_field_including_network_must_be_explicit(field: str) -> None:
    payload = dict(REQUIRED)
    del payload[field]
    with pytest.raises(ValidationError):
        WithdrawalLinkRequest.model_validate(payload)


@pytest.mark.parametrize("field", [*REQUIRED, "comment", "platform"])
def test_no_request_property_is_nullable(field: str) -> None:
    with pytest.raises(ValidationError):
        _body(**{field: None})


@pytest.mark.parametrize("field,maximum", [("address", 100), ("comment", 50)])
def test_only_documented_string_maxima_apply(field: str, maximum: int) -> None:
    assert json.loads(serialize_request(_body(**{field: "ю" * maximum})))[field] == "ю" * maximum
    with pytest.raises(ValidationError):
        _body(**{field: "ю" * (maximum + 1)})


@pytest.mark.parametrize("field", ["asset", "platform"])
def test_unbounded_strings_do_not_borrow_other_dto_limits(field: str) -> None:
    assert json.loads(serialize_request(_body(**{field: "x" * 1001})))[field] == "x" * 1001


@pytest.mark.parametrize("amount", [Decimal(EXACT_AMOUNT), "1E-40", "-0.0000", "0", "-1.0001"])
def test_money_is_exact_without_invented_bounds(amount: str | Decimal) -> None:
    assert json.loads(serialize_request(_body(amount=amount)))["amount"] == str(Decimal(amount))


@pytest.mark.parametrize("amount", [0, 1, 0.1, True, b"1", "", "NaN", "Infinity", Decimal("NaN")])
def test_money_rejects_coercion_and_non_finite_values(amount: Any) -> None:
    with pytest.raises(ValidationError):
        _body(amount=amount)


@pytest.mark.parametrize(
    "changes",
    [
        {"network": "ton"},
        {"network": "future"},
        {"address": 123},
        {"asset": True},
        {"comment": 123},
        {"platform": 123},
        {"clientWithdrawalId": "direct-only"},
        {"callback": {}},
        {"webLink": "response-only"},
    ],
)
def test_strict_request_does_not_mix_response_or_direct_withdrawal_fields(
    changes: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        _body(**changes)


@pytest.mark.parametrize("kind", ["dict", "response", "direct", "null"])
async def test_resource_requires_its_request_type_before_io(asynchronous: bool, kind: str) -> None:
    bodies = {
        "dict": REQUIRED,
        "response": WithdrawalLink(),
        "null": None,
        "direct": WithdrawalCreateRequest.model_validate({**REQUIRED, "clientWithdrawalId": "id"}),
    }

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("A wrong request type reached HTTP")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(TypeError):
            await _resolve(client.withdrawal_links.create(request=bodies[kind]))


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", 0.1),
        ("network", "future"),
        ("address", "x" * 101),
        ("comment", "x" * 51),
        ("platform", None),
    ],
)
@pytest.mark.parametrize("constructed", [False, True], ids=["mutated", "constructed"])
async def test_request_bypasses_are_revalidated_before_io(
    asynchronous: bool, field: str, value: Any, constructed: bool
) -> None:
    if constructed:
        body = WithdrawalLinkRequest.model_construct(
            **{**REQUIRED, "amount": Decimal("1"), field: value}
        )
    else:
        body = _body()
        setattr(body, field, value)

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An invalid request bypass reached HTTP")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.withdrawal_links.create(request=body))


@pytest.mark.parametrize("field", list(REQUIRED))
async def test_constructed_missing_required_fields_are_revalidated(
    asynchronous: bool, field: str
) -> None:
    payload: dict[str, Any] = {**REQUIRED, "amount": Decimal("1")}
    del payload[field]
    body = WithdrawalLinkRequest.model_construct(**payload)

    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("A missing required field reached HTTP")

    async with _client(asynchronous, unexpected) as client:
        with pytest.raises(ValidationError):
            await _resolve(client.withdrawal_links.create(request=body))


def test_required_wire_values_survive_empty_fields_set_without_mutating_input() -> None:
    body = WithdrawalLinkRequest.model_construct(
        _fields_set=set(), **{**REQUIRED, "amount": Decimal("1.2300")}
    )
    assert json.loads(serialize_request(body)) == REQUIRED
    assert body.model_fields_set == set()


async def test_missing_sdk_auth_fails_before_io(asynchronous: bool) -> None:
    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("An unauthenticated request reached HTTP")

    async with _client(asynchronous, unexpected, token=None) as client:
        with pytest.raises(AuthenticationError):
            await _resolve(client.withdrawal_links.create(request=_body()))


@pytest.mark.parametrize("status", [201, 202, 204])
async def test_only_exact_200_succeeds(asynchronous: bool, status: int) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(status, json=LINKS)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.withdrawal_links.create(request=_body()))


@pytest.mark.parametrize("content", [b"", b"null", b"[]", b'"text"', b"not json"])
async def test_success_requires_a_json_object(asynchronous: bool, content: bytes) -> None:
    async with _client(asynchronous, lambda _: httpx.Response(200, content=content)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(client.withdrawal_links.create(request=_body()))


@pytest.mark.parametrize(
    "status,error,problem_type",
    [
        (400, APIError, "network_is_suspended"),
        (400, APIError, "amount_less_than_minimum"),
        (400, APIError, "withdrawal_incorrect_comment"),
        (400, APIError, "withdrawal_incorrect_address"),
        (400, APIError, "withdrawal_asset_not_allowed"),
        (401, AuthenticationError, "unauthorized"),
        (404, NotFoundError, "asset_not_found"),
        (404, NotFoundError, "network_not_found"),
        (429, RateLimitError, "rate_limit_exceeded"),
        (500, ServerError, "internal_error"),
    ],
)
async def test_documented_errors_preserve_problem_metadata_without_retry(
    asynchronous: bool, status: int, error: type[APIError], problem_type: str
) -> None:
    calls: list[httpx.Request] = []
    problem = {
        "status": status,
        "type": f"/api/problems/{problem_type}",
        "future": {"retained": True},
    }

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status, json=problem, headers={"x-request-id": "link-request", "retry-after": "9"}
        )

    async with _client(asynchronous, respond) as client:
        with pytest.raises(error) as caught:
            await _resolve(client.withdrawal_links.create(request=_body()))
    assert type(caught.value) is error
    assert caught.value.status_code == status
    assert caught.value.problem == problem
    assert caught.value.request_id == "link-request"
    assert caught.value.retry_after == "9"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "failure", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout]
)
async def test_timeout_leaves_creation_unknown_after_one_attempt(
    asynchronous: bool, failure: type[httpx.TimeoutException]
) -> None:
    calls: list[httpx.Request] = []

    def fail(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise failure("Synthetic uncertain result", request=request)

    async with _client(asynchronous, fail) as client:
        with pytest.raises(RequestTimeoutError):
            await _resolve(client.withdrawal_links.create(request=_body()))
    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert calls[0].url.path == "/api/v1/withdrawal-link"


async def test_redirect_is_not_followed(asynchronous: bool) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(307, headers={"location": "https://example.invalid/sink"})

    async with _client(asynchronous, respond, follow_redirects=True) as client:
        with pytest.raises(APIError) as caught:
            await _resolve(client.withdrawal_links.create(request=_body()))
    assert caught.value.status_code == 307
    assert len(calls) == 1


async def test_shared_session_keeps_auth_defaults_and_ownership(asynchronous: bool) -> None:
    calls: list[httpx.Request] = []
    http_cls = httpx.AsyncClient if asynchronous else httpx.Client
    client_cls = AsyncPayClient if asynchronous else PayClient
    auth = httpx.BasicAuth("unrelated", "synthetic-password")

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    http = http_cls(
        transport=httpx.MockTransport(respond),
        auth=auth,
        headers={"Authorization": "Bearer unrelated", "X-Custom": "retained"},
        timeout=77,
        follow_redirects=True,
    )
    original_headers = dict(http.headers)
    original_timeout = http.timeout
    try:
        for token in ("synthetic-first", "synthetic-second", None):
            client = client_cls(
                api_token=token, environment="testnet", timeout=12, http_client=http
            )
            try:
                if token is None:
                    with pytest.raises(AuthenticationError):
                        await _resolve(client.withdrawal_links.create(request=_body()))
                else:
                    await _resolve(client.withdrawal_links.create(request=_body()))
            finally:
                await _resolve(client.aclose() if asynchronous else client.close())
        assert not http.is_closed
        assert dict(http.headers) == original_headers
        assert http.timeout == original_timeout
        assert http.auth is auth
        assert http.follow_redirects is True
    finally:
        await _resolve(http.aclose() if asynchronous else http.close())
    assert [r.headers["authorization"] for r in calls] == [
        "Bearer synthetic-first",
        "Bearer synthetic-second",
    ]
    for request in calls:
        assert request.headers["x-custom"] == "retained"
        assert request.extensions["timeout"] == {"connect": 12, "read": 12, "write": 12, "pool": 12}


def test_public_exports_and_sync_async_signatures() -> None:
    for name in ("WithdrawalLinkRequest", "WithdrawalLink"):
        assert name in pay.__all__ and name in models.__all__
        assert getattr(pay, name) is getattr(models, name)
    assert issubclass(WithdrawalLinkRequest, RequestModel)
    assert not issubclass(WithdrawalLink, RequestModel)
    sync = inspect.signature(WithdrawalLinksResource.create)
    asynchronous = inspect.signature(AsyncWithdrawalLinksResource.create)
    assert sync == asynchronous
    assert set(sync.parameters) == {"self", "request"}
    assert sync.parameters["request"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sync.parameters["request"].default is inspect.Parameter.empty
    assert not inspect.iscoroutinefunction(WithdrawalLinksResource.create)
    assert inspect.iscoroutinefunction(AsyncWithdrawalLinksResource.create)
