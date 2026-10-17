"""Synthetic Current Pay payout read contracts, shared by both clients."""

import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from xrocket import (
    APIError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ResponseValidationError,
    ServerError,
    pay,
)
from xrocket.pay import AsyncPayClient, CursorPage, PayClient, Payout, PayoutCallback, models

Client = PayClient | AsyncPayClient
Handler = Callable[[httpx.Request], httpx.Response]
FROM_DATE = datetime.fromisoformat("2026-10-16T21:02:03.123456-07:00")
TO_DATE = datetime.fromisoformat("2026-10-17T09:10:11+05:00")
EXACT_AMOUNT = "12345678901234567890.1234567890123456789000"


def _payout(**overrides: Any) -> dict[str, Any]:
    return {
        "payoutId": "000-payout",
        "target": "000-target",
        "targetType": "telegram_user_id",
        "asset": "USDT",
        "amount": EXACT_AMOUNT,
        "status": "pending",
        **overrides,
    }


def _page(items: list[dict[str, Any]], next_cursor: str | None = None) -> dict[str, Any]:
    return {"items": items, "pagination": {"total": len(items), "next": next_cursor}}


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


@pytest.mark.parametrize("name", ["Payout", "PayoutCallback"])
def test_payout_models_share_public_exports(name: str) -> None:
    assert name in pay.__all__
    assert name in models.__all__
    assert getattr(pay, name) is getattr(models, name)


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("list", ["from_date", "to_date", "cursor", "limit"]),
        ("retrieve", ["payout_id", "client_payout_id"]),
    ],
)
async def test_payout_sync_async_signatures_match(method: str, expected: list[str]) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("Inspecting resource signatures reached the network")

    async with (
        _sdk("sync", unexpected_request) as sync,
        _sdk("async", unexpected_request) as asynchronous,
    ):
        sync_method = getattr(sync.payouts, method)
        async_method = getattr(asynchronous.payouts, method)
        assert inspect.signature(sync_method) == inspect.signature(async_method)
        parameters = inspect.signature(sync_method).parameters
        assert list(parameters) == expected
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
        assert all(p.default is None for p in parameters.values())
        assert not inspect.iscoroutinefunction(sync_method)
        assert inspect.iscoroutinefunction(async_method)


@pytest.mark.parametrize(
    ("method", "kwargs", "path", "wire"),
    [
        ("list", {}, "/api/v1/payouts", {}),
        (
            "list",
            {"from_date": None, "to_date": None, "cursor": None, "limit": None},
            "/api/v1/payouts",
            {},
        ),
        (
            "list",
            {
                "from_date": FROM_DATE,
                "to_date": TO_DATE,
                "cursor": "opaque+/= cursor?&\u2603",
                "limit": 1,
            },
            "/api/v1/payouts",
            {
                "fromDate": FROM_DATE.isoformat(),
                "toDate": TO_DATE.isoformat(),
                "cursor": "opaque+/= cursor?&\u2603",
                "limit": "1",
            },
        ),
        (
            "list",
            {"from_date": FROM_DATE},
            "/api/v1/payouts",
            {"fromDate": FROM_DATE.isoformat()},
        ),
        (
            "list",
            {"to_date": TO_DATE, "cursor": ""},
            "/api/v1/payouts",
            {"toDate": TO_DATE.isoformat(), "cursor": ""},
        ),
        (
            "list",
            {"from_date": TO_DATE, "to_date": FROM_DATE},
            "/api/v1/payouts",
            {"fromDate": TO_DATE.isoformat(), "toDate": FROM_DATE.isoformat()},
        ),
        *(
            ("list", {"limit": limit}, "/api/v1/payouts", {"limit": str(limit)})
            for limit in (0, -1, 1001)
        ),
        (
            "retrieve",
            {"payout_id": "p"},
            "/api/v1/payout",
            {"payoutId": "p"},
        ),
        (
            "retrieve",
            {"payout_id": "000-payout", "client_payout_id": None},
            "/api/v1/payout",
            {"payoutId": "000-payout"},
        ),
        (
            "retrieve",
            {"payout_id": None, "client_payout_id": "order /+?"},
            "/api/v1/payout",
            {"clientPayoutId": "order /+?"},
        ),
        (
            "retrieve",
            {"payout_id": "payout", "client_payout_id": "client-payout"},
            "/api/v1/payout",
            {"payoutId": "payout", "clientPayoutId": "client-payout"},
        ),
        (
            "retrieve",
            {"payout_id": "p" * 100, "client_payout_id": "o" * 100},
            "/api/v1/payout",
            {"payoutId": "p" * 100, "clientPayoutId": "o" * 100},
        ),
    ],
)
async def test_payout_routes_queries_and_minimal_response(
    backend: str, method: str, kwargs: dict[str, Any], path: str, wire: dict[str, str]
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_page([_payout()]) if method == "list" else _payout())

    async with _sdk(backend, respond) as client:
        result = await _resolve(getattr(client.payouts, method)(**kwargs))

    assert len(calls) == 1
    request = calls[0]
    assert request.method == "GET"
    assert request.url.host == "pay.api.testnet.xrocket.exchange"
    assert request.url.path == path
    assert dict(request.url.params) == wire
    assert request.headers["Authorization"] == "Bearer synthetic-test-token"
    assert request.headers["Accept"] == "application/json"
    assert "Rocket-Pay-Key" not in request.headers
    if method == "list":
        assert isinstance(result, CursorPage)
        result = result.items[0]
    assert isinstance(result, Payout)
    assert result.payout_id == "000-payout"
    assert result.target == "000-target"
    assert result.target_type == "telegram_user_id"
    assert result.asset == "USDT"
    assert result.status == "pending"
    assert isinstance(result.amount, Decimal)
    assert str(result.amount) == EXACT_AMOUNT
    assert result.client_payout_id is result.description is result.callback is None


@pytest.mark.parametrize("next_cursor", [None, "next+/= cursor"])
@pytest.mark.parametrize("item_count", [0, 1])
async def test_payout_pagination_returns_one_page_without_following_next(
    backend: str, next_cursor: str | None, item_count: int
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_page([_payout()] * item_count, next_cursor))

    async with _sdk(backend, respond) as client:
        page = await _resolve(client.payouts.list(limit=1))

    assert len(calls) == 1
    assert len(page.items) == item_count
    assert page.pagination.total == item_count
    assert page.pagination.next == next_cursor


@pytest.mark.parametrize("method", ["list", "retrieve"])
async def test_payout_nested_response_preserves_unknown_status_and_fields(
    backend: str, method: str
) -> None:
    payload = _payout(
        clientPayoutId="client-synthetic",
        description="Synthetic fixture",
        targetType="future_target",
        status="future_status",
        callback={
            "callbackUrl": "https://example.invalid/callback",
            "payload": {"order": "synthetic", "nested": {"items": [1, True, None]}},
            "callbackExtra": True,
        },
        futureField={"version": 2},
    )
    response = _page([payload]) if method == "list" else payload
    if method == "list":
        response["pageExtra"] = True
        response["pagination"]["cursorVersion"] = 2
    kwargs = {} if method == "list" else {"payout_id": "payout"}
    async with _sdk(backend, lambda _: httpx.Response(200, json=response)) as client:
        result = await _resolve(getattr(client.payouts, method)(**kwargs))
    if method == "list":
        assert result.model_extra == {"pageExtra": True}
        assert result.pagination.model_extra == {"cursorVersion": 2}
        result = result.items[0]

    assert isinstance(result, Payout)
    assert result.client_payout_id == "client-synthetic"
    assert result.description == "Synthetic fixture"
    assert result.target_type == "future_target"
    assert result.status == "future_status"
    assert result.model_extra == {"futureField": {"version": 2}}
    assert isinstance(result.callback, PayoutCallback)
    assert result.callback.callback_url == "https://example.invalid/callback"
    assert result.callback.payload == payload["callback"]["payload"]
    assert result.callback.model_extra == {"callbackExtra": True}
    dumped = result.model_dump(mode="json", by_alias=True)
    assert dumped["payoutId"] == "000-payout"
    assert dumped["clientPayoutId"] == "client-synthetic"
    assert dumped["targetType"] == "future_target"
    assert dumped["amount"] == EXACT_AMOUNT
    assert dumped["callback"]["callbackUrl"] == "https://example.invalid/callback"


@pytest.mark.parametrize(
    "callback", [{}, {"callbackUrl": "https://example.invalid/callback"}, {"payload": {}}]
)
def test_payout_callback_fields_are_independently_optional(callback: dict[str, Any]) -> None:
    payout = Payout.model_validate(_payout(callback=callback))
    assert isinstance(payout.callback, PayoutCallback)
    assert payout.callback.callback_url == callback.get("callbackUrl")
    assert payout.callback.payload == callback.get("payload")


@pytest.mark.parametrize(
    "field", ["payoutId", "target", "targetType", "asset", "amount", "status"]
)
def test_payout_requires_documented_required_fields(field: str) -> None:
    payload = _payout()
    del payload[field]
    with pytest.raises(ValidationError):
        Payout.model_validate(payload)


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("retrieve", {}),
        ("retrieve", {"payout_id": None, "client_payout_id": None}),
        *(
            ("retrieve", {field: value})
            for field in ("payout_id", "client_payout_id")
            for value in ("", "x" * 101, 123, True)
        ),
        ("retrieve", {"payout_id": "valid", "client_payout_id": ""}),
        ("retrieve", {"payout_id": "", "client_payout_id": "valid"}),
        *(("list", {"limit": value}) for value in (True, False, 1.5, "1")),
        *(
            ("list", {field: value})
            for field in ("from_date", "to_date")
            for value in (datetime(2026, 10, 17), date(2026, 10, 17), "2026-10-17T09:00:00Z")
        ),
    ],
)
async def test_invalid_payout_arguments_fail_before_network(
    backend: str, method: str, kwargs: dict[str, Any]
) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid payout arguments reached the network")

    async with _sdk(backend, unexpected_request) as client:
        with pytest.raises(ValueError):
            await _resolve(getattr(client.payouts, method)(**kwargs))


@pytest.mark.parametrize("method", ["list", "retrieve"])
async def test_payout_reads_require_sdk_auth_before_network(backend: str, method: str) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("An unauthenticated payout request reached the network")

    kwargs = {} if method == "list" else {"payout_id": "payout"}
    async with _sdk(backend, unexpected_request, api_token=None) as client:
        with pytest.raises(AuthenticationError):
            await _resolve(getattr(client.payouts, method)(**kwargs))


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("retrieve", {}),
        ("retrieve", _payout(amount=0.1)),
        ("retrieve", _payout(amount=True)),
        ("retrieve", _payout(amount="NaN")),
        ("retrieve", _payout(callback={"payload": ["not-an-object"]})),
        ("list", {"items": [_payout()], "pagination": {}}),
        ("list", {"items": [_payout()], "pagination": {"total": 1}}),
        ("list", _page([{}])),
        ("list", _page([_payout(amount=0.1)])),
        ("list", {"pagination": {"total": 0, "next": None}}),
    ],
)
async def test_malformed_payout_responses_use_shared_validation_error(
    backend: str, method: str, payload: dict[str, Any]
) -> None:
    kwargs = {} if method == "list" else {"payout_id": "payout"}
    async with _sdk(backend, lambda _: httpx.Response(200, json=payload)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(getattr(client.payouts, method)(**kwargs))


@pytest.mark.parametrize(
    ("method", "status", "error_type"),
    [
        ("list", 400, APIError),
        ("retrieve", 400, APIError),
        ("list", 401, AuthenticationError),
        ("retrieve", 401, AuthenticationError),
        ("retrieve", 404, NotFoundError),
        ("list", 429, RateLimitError),
        ("retrieve", 429, RateLimitError),
        ("list", 500, ServerError),
        ("retrieve", 500, ServerError),
    ],
)
async def test_payout_http_errors_preserve_problem_without_retry(
    backend: str, method: str, status: int, error_type: type[APIError]
) -> None:
    calls: list[httpx.Request] = []
    problem = {"status": status, "kind": "synthetic", "detail": "Synthetic failure"}

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=problem, headers={"x-request-id": "payout-request"})

    kwargs = {} if method == "list" else {"payout_id": "payout"}
    async with _sdk(backend, respond) as client:
        with pytest.raises(error_type) as caught:
            await _resolve(getattr(client.payouts, method)(**kwargs))

    assert type(caught.value) is error_type
    assert caught.value.status_code == status
    assert caught.value.problem == problem
    assert caught.value.request_id == "payout-request"
    assert len(calls) == 1
