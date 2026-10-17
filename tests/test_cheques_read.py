"""Synthetic Current Pay cheque read contracts, shared by both clients."""

import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date, datetime
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
from xrocket.pay import (
    AsyncPayClient,
    Cheque,
    ChequeCallback,
    ChequeLinks,
    ChequeURL,
    CursorPage,
    PayClient,
    models,
)

Client = PayClient | AsyncPayClient
Handler = Callable[[httpx.Request], httpx.Response]
FROM_DATE = datetime.fromisoformat("2026-10-16T21:02:03.123456-07:00")
TO_DATE = datetime.fromisoformat("2026-10-17T09:10:11+05:00")


def _cheque(**overrides: Any) -> dict[str, Any]:
    return {"chequeId": "000-cheque", "asset": "USDT", "links": {}, "deleted": False, **overrides}


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


@pytest.mark.parametrize("name", ["Cheque", "ChequeLinks", "ChequeCallback", "ChequeURL"])
def test_cheque_models_share_public_exports(name: str) -> None:
    assert name in pay.__all__
    assert name in models.__all__
    assert getattr(pay, name) is getattr(models, name)


@pytest.mark.parametrize(
    ("method", "kwargs", "path", "wire"),
    [
        ("list", {}, "/api/v1/cheques", {}),
        (
            "list",
            {
                "from_date": FROM_DATE,
                "to_date": TO_DATE,
                "target_type": "telegram_user_id",
                "target": "000 /+?",
                "state": "active",
                "cursor": "opaque+/= cursor?&\u2603",
                "limit": 1,
            },
            "/api/v1/cheques",
            {
                "fromDate": FROM_DATE.isoformat(),
                "toDate": TO_DATE.isoformat(),
                "targetType": "telegram_user_id",
                "target": "000 /+?",
                "state": "active",
                "cursor": "opaque+/= cursor?&\u2603",
                "limit": "1",
            },
        ),
        (
            "list",
            {"target_type": "user_id", "target": "", "state": "completed", "cursor": ""},
            "/api/v1/cheques",
            {"targetType": "user_id", "target": "", "state": "completed", "cursor": ""},
        ),
        (
            "list",
            {"target_type": "telegram_username", "target": "x" * 100, "state": "draft"},
            "/api/v1/cheques",
            {"targetType": "telegram_username", "target": "x" * 100, "state": "draft"},
        ),
        (
            "list",
            {"state": "error", "limit": 1000},
            "/api/v1/cheques",
            {"state": "error", "limit": "1000"},
        ),
        (
            "retrieve",
            {"cheque_id": "000-cheque"},
            "/api/v1/cheque",
            {"chequeId": "000-cheque"},
        ),
        (
            "retrieve",
            {"client_cheque_id": "order /+?"},
            "/api/v1/cheque",
            {"clientChequeId": "order /+?"},
        ),
        (
            "retrieve",
            {"cheque_id": "cheque", "client_cheque_id": "client-cheque"},
            "/api/v1/cheque",
            {"chequeId": "cheque", "clientChequeId": "client-cheque"},
        ),
        (
            "retrieve",
            {"cheque_id": "c" * 100, "client_cheque_id": "o" * 100},
            "/api/v1/cheque",
            {"chequeId": "c" * 100, "clientChequeId": "o" * 100},
        ),
    ],
)
async def test_cheque_routes_queries_and_minimal_response(
    backend: str, method: str, kwargs: dict[str, Any], path: str, wire: dict[str, str]
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_page([_cheque()]) if method == "list" else _cheque())

    async with _sdk(backend, respond) as client:
        result = await _resolve(getattr(client.cheques, method)(**kwargs))

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
    assert isinstance(result, Cheque)
    assert result.cheque_id == "000-cheque"
    assert result.asset == "USDT"
    assert result.deleted is False
    assert result.state is result.client_cheque_id is result.description is None
    assert result.target_type is result.target is result.callback is result.url is None
    assert isinstance(result.links, ChequeLinks)
    assert result.links.model_dump() == {
        "telegram_bot_link": None,
        "telegram_mini_app_link": None,
        "web_link": None,
    }


@pytest.mark.parametrize("next_cursor", [None, "next+/= cursor"])
@pytest.mark.parametrize("item_count", [0, 1])
async def test_cheque_pagination_returns_one_page_without_following_next(
    backend: str, next_cursor: str | None, item_count: int
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_page([_cheque()] * item_count, next_cursor))

    async with _sdk(backend, respond) as client:
        page = await _resolve(client.cheques.list(limit=1))

    assert len(calls) == 1
    assert len(page.items) == item_count
    assert page.pagination.total == item_count
    assert page.pagination.next == next_cursor


@pytest.mark.parametrize("method", ["list", "retrieve"])
async def test_cheque_nested_response_preserves_unknown_state_and_fields(
    backend: str, method: str
) -> None:
    payload = _cheque(
        clientChequeId="client-synthetic",
        description="Synthetic fixture",
        targetType="future_target",
        target="000-target",
        state="future_state",
        deleted=True,
        links={
            "telegramBotLink": "https://t.me/xRocket?start=synthetic",
            "telegramMiniAppLink": "https://t.me/xRocket?startapp=synthetic",
            "webLink": "https://example.invalid/activate",
            "futureLink": "retained",
        },
        callback={
            "callbackUrl": "https://example.invalid/callback",
            "payload": {"order": "synthetic", "nested": {"items": [1, True, None]}},
            "callbackExtra": True,
        },
        url={
            "successUrl": "https://example.invalid/success",
            "cancelUrl": "https://example.invalid/cancel",
            "urlExtra": 2,
        },
        amount="123.4500",
        futureField={"version": 2},
    )
    response = _page([payload]) if method == "list" else payload
    if method == "list":
        response["pageExtra"] = True
        response["pagination"]["cursorVersion"] = 2
    kwargs = {} if method == "list" else {"cheque_id": "cheque"}
    async with _sdk(backend, lambda _: httpx.Response(200, json=response)) as client:
        result = await _resolve(getattr(client.cheques, method)(**kwargs))
    if method == "list":
        assert result.model_extra == {"pageExtra": True}
        assert result.pagination.model_extra == {"cursorVersion": 2}
        result = result.items[0]

    assert isinstance(result, Cheque)
    assert result.client_cheque_id == "client-synthetic"
    assert result.description == "Synthetic fixture"
    assert result.target_type == "future_target"
    assert result.target == "000-target"
    assert result.state == "future_state"
    assert result.deleted is True
    assert result.model_extra == {"amount": "123.4500", "futureField": {"version": 2}}
    assert isinstance(result.links, ChequeLinks)
    assert result.links.telegram_bot_link == payload["links"]["telegramBotLink"]
    assert result.links.telegram_mini_app_link == payload["links"]["telegramMiniAppLink"]
    assert result.links.web_link == payload["links"]["webLink"]
    assert result.links.model_extra == {"futureLink": "retained"}
    assert isinstance(result.callback, ChequeCallback)
    assert result.callback.callback_url == "https://example.invalid/callback"
    assert result.callback.payload == payload["callback"]["payload"]
    assert result.callback.model_extra == {"callbackExtra": True}
    assert isinstance(result.url, ChequeURL)
    assert result.url.success_url == "https://example.invalid/success"
    assert result.url.cancel_url == "https://example.invalid/cancel"
    assert result.url.model_extra == {"urlExtra": 2}


def test_empty_optional_cheque_objects_are_valid() -> None:
    cheque = Cheque.model_validate(_cheque(callback={}, url={}))
    assert isinstance(cheque.callback, ChequeCallback)
    assert cheque.callback.callback_url is cheque.callback.payload is None
    assert isinstance(cheque.url, ChequeURL)
    assert cheque.url.success_url is cheque.url.cancel_url is None


@pytest.mark.parametrize("field", ["chequeId", "asset", "links", "deleted"])
def test_cheque_requires_only_documented_required_fields(field: str) -> None:
    payload = _cheque()
    del payload[field]
    with pytest.raises(ValidationError):
        Cheque.model_validate(payload)


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("retrieve", {}),
        *(
            ("retrieve", {field: value})
            for field in ("cheque_id", "client_cheque_id")
            for value in ("", "x" * 101, 123, True)
        ),
        ("retrieve", {"cheque_id": "valid", "client_cheque_id": ""}),
        ("retrieve", {"cheque_id": "", "client_cheque_id": "valid"}),
        ("list", {"target_type": "user_id"}),
        ("list", {"target": "synthetic"}),
        ("list", {"target_type": "future_target", "target": "synthetic"}),
        ("list", {"target_type": "user_id", "target": "x" * 101}),
        ("list", {"target_type": "user_id", "target": 123}),
        ("list", {"state": "future_state"}),
        *(("list", {"limit": value}) for value in (0, -1, 1001, True, 1.5, "1")),
        *(
            ("list", {field: value})
            for field in ("from_date", "to_date")
            for value in (datetime(2026, 10, 17), date(2026, 10, 17), "2026-10-17T09:00:00Z")
        ),
    ],
)
async def test_invalid_cheque_arguments_fail_before_network(
    backend: str, method: str, kwargs: dict[str, Any]
) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid cheque arguments reached the network")

    async with _sdk(backend, unexpected_request) as client:
        with pytest.raises(ValueError):
            await _resolve(getattr(client.cheques, method)(**kwargs))


@pytest.mark.parametrize("method", ["list", "retrieve"])
async def test_cheque_reads_require_sdk_auth_before_network(backend: str, method: str) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("An unauthenticated cheque request reached the network")

    kwargs = {} if method == "list" else {"cheque_id": "cheque"}
    async with _sdk(backend, unexpected_request, api_token=None) as client:
        with pytest.raises(AuthenticationError):
            await _resolve(getattr(client.cheques, method)(**kwargs))


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("retrieve", {}),
        ("retrieve", _cheque(links=None)),
        ("retrieve", _cheque(callback={"payload": ["not-an-object"]})),
        ("list", {"items": [_cheque()], "pagination": {}}),
        ("list", _page([{}])),
        ("list", {"pagination": {"total": 0, "next": None}}),
    ],
)
async def test_malformed_cheque_responses_use_shared_validation_error(
    backend: str, method: str, payload: dict[str, Any]
) -> None:
    kwargs = {} if method == "list" else {"cheque_id": "cheque"}
    async with _sdk(backend, lambda _: httpx.Response(200, json=payload)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(getattr(client.cheques, method)(**kwargs))


@pytest.mark.parametrize("method", ["list", "retrieve"])
@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, APIError),
        (401, AuthenticationError),
        (404, NotFoundError),
        (429, RateLimitError),
        (500, ServerError),
    ],
)
async def test_cheque_http_errors_preserve_problem_without_retry(
    backend: str, method: str, status: int, error_type: type[APIError]
) -> None:
    calls: list[httpx.Request] = []
    problem = {"status": status, "kind": "synthetic", "detail": "Synthetic failure"}

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=problem, headers={"x-request-id": "cheque-request"})

    kwargs = {} if method == "list" else {"cheque_id": "cheque"}
    async with _sdk(backend, respond) as client:
        with pytest.raises(error_type) as caught:
            await _resolve(getattr(client.cheques, method)(**kwargs))

    assert type(caught.value) is error_type
    assert caught.value.status_code == status
    assert caught.value.problem == problem
    assert caught.value.request_id == "cheque-request"
    assert len(calls) == 1
