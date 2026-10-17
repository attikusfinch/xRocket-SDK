"""HTTP behavior shared by the synchronous and asynchronous Pay clients."""

import inspect
import traceback
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from pydantic import TypeAdapter

from xrocket import (
    APIError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    RequestTimeoutError,
    ResponseValidationError,
    ServerError,
    TransportError,
    XRocketError,
)
from xrocket._core.transport import AsyncTransport, SyncTransport
from xrocket.pay import AsyncPayClient, PayClient

TOKEN = "synthetic-secret-token-for-transport-tests"
APP = {"id": "test-app", "name": "SDK tests"}
Client = PayClient | AsyncPayClient
Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(params=("sync", "async"))
def backend(request: pytest.FixtureRequest) -> str:
    return str(request.param)


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def _close(client: Client) -> None:
    if isinstance(client, AsyncPayClient):
        await client.aclose()
    else:
        client.close()


@asynccontextmanager
async def _sdk(
    backend: str, handler: Handler, **options: Any
) -> AsyncIterator[tuple[Client, httpx.Client | httpx.AsyncClient]]:
    transport = httpx.MockTransport(handler)
    if backend == "async":
        http: httpx.Client | httpx.AsyncClient = httpx.AsyncClient(transport=transport)
        client: Client = AsyncPayClient(http_client=http, **options)
    else:
        http = httpx.Client(transport=transport)
        client = PayClient(http_client=http, **options)
    try:
        yield client, http
    finally:
        await _close(client)
        if isinstance(http, httpx.AsyncClient):
            await http.aclose()
        else:
            http.close()


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, APIError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (408, APIError),
        (409, APIError),
        (422, APIError),
        (429, RateLimitError),
        (500, ServerError),
        (502, ServerError),
        (503, ServerError),
    ],
)
async def test_http_error_classification_preserves_problem_and_metadata(
    backend: str, status: int, error_type: type[APIError]
) -> None:
    calls: list[httpx.Request] = []
    problem = {"status": status, "kind": "synthetic", "detail": TOKEN}

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            json=problem,
            headers={"x-request-id": "req-test", "retry-after": "7"},
        )

    async with _sdk(backend, respond, api_token=TOKEN) as (client, _):
        with pytest.raises(error_type) as caught:
            await _resolve(client.app.info())

    error = caught.value
    assert type(error) is error_type
    assert isinstance(error, XRocketError)
    assert error.status_code == status
    assert error.problem == problem
    assert error.request_id == "req-test"
    assert error.retry_after == "7"
    assert TOKEN not in str(error)
    assert TOKEN not in repr(error)
    assert len(calls) == 1, "The first implementation must not silently retry requests"


@pytest.mark.parametrize("status", [400, 401, 429, 502])
async def test_html_error_keeps_http_status_without_exposing_body(
    backend: str, status: int
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            text=f"<html>upstream failed: {TOKEN}</html>",
            headers={"content-type": "text/html", "x-request-id": "proxy-request"},
        )

    async with _sdk(backend, respond) as (client, _):
        with pytest.raises(APIError) as caught:
            await _resolve(client.currencies.list())

    assert caught.value.status_code == status
    assert caught.value.problem == {}
    assert caught.value.request_id == "proxy-request"
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize("body", [b"[", b"<html>not JSON</html>", b"{}", b"null"])
async def test_invalid_success_response_is_validation_error(backend: str, body: bytes) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    async with _sdk(backend, respond, api_token=TOKEN) as (client, _):
        with pytest.raises(ResponseValidationError) as caught:
            await _resolve(client.app.info())

    assert isinstance(caught.value, XRocketError)


@pytest.mark.parametrize(
    ("failure_type", "error_type"),
    [
        (httpx.ConnectError, TransportError),
        (httpx.ReadError, TransportError),
        (httpx.ConnectTimeout, RequestTimeoutError),
        (httpx.ReadTimeout, RequestTimeoutError),
        (httpx.PoolTimeout, RequestTimeoutError),
    ],
)
async def test_network_errors_are_safe_and_original_context_is_inspectable(
    backend: str, failure_type: type[httpx.RequestError], error_type: type[TransportError]
) -> None:
    failures: list[httpx.RequestError] = []

    def fail(request: httpx.Request) -> httpx.Response:
        error = failure_type(f"upstream exception containing {TOKEN}", request=request)
        failures.append(error)
        raise error

    async with _sdk(backend, fail, api_token=TOKEN) as (client, _):
        with pytest.raises(error_type) as caught:
            await _resolve(client.app.info())

    assert type(caught.value) is error_type
    assert isinstance(caught.value, XRocketError)
    assert caught.value.__context__ is failures[0]
    assert TOKEN not in str(caught.value)
    assert TOKEN not in repr(caught.value)
    assert TOKEN not in "".join(traceback.format_exception(caught.value))
    assert len(failures) == 1


@pytest.mark.parametrize("status", [301, 302, 307, 308])
async def test_redirect_never_follows_injected_client_defaults(backend: str, status: int) -> None:
    calls: list[httpx.Request] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, headers={"location": "https://redirect.invalid/token-sink"})

    async with _sdk(backend, redirect, api_token=TOKEN) as (client, http):
        http.follow_redirects = True
        with pytest.raises(APIError) as caught:
            await _resolve(client.app.info())
        assert http.follow_redirects is True

    assert caught.value.status_code == status
    assert len(calls) == 1
    assert calls[0].url.host == "pay.api.xrocket.exchange"


async def test_private_request_requires_token_before_network(backend: str) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=APP)

    async with _sdk(backend, respond) as (client, _):
        with pytest.raises(AuthenticationError):
            await _resolve(client.app.info())

    assert calls == []


async def test_public_request_does_not_require_or_invent_token(backend: str) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=[])

    async with _sdk(backend, respond) as (client, _):
        result = await _resolve(client.currencies.list())

    assert result == []
    assert len(calls) == 1
    assert "authorization" not in calls[0].headers


@pytest.mark.parametrize(
    ("options", "expected_url"),
    [
        ({}, "https://pay.api.xrocket.exchange/api/v1/app-info"),
        ({"environment": "mainnet"}, "https://pay.api.xrocket.exchange/api/v1/app-info"),
        ({"environment": "testnet"}, "https://pay.api.testnet.xrocket.exchange/api/v1/app-info"),
        ({"base_url": "https://custom.example/"}, "https://custom.example/api/v1/app-info"),
        ({"base_url": "http://localhost:8000"}, "http://localhost:8000/api/v1/app-info"),
        ({"base_url": "http://127.0.0.1:8000/"}, "http://127.0.0.1:8000/api/v1/app-info"),
        ({"base_url": "http://[::1]:8000"}, "http://[::1]:8000/api/v1/app-info"),
    ],
)
async def test_exact_url_authorization_and_explicit_timeout(
    backend: str, options: dict[str, str], expected_url: str
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=APP)

    async with _sdk(backend, respond, api_token=TOKEN, **options) as (client, _):
        result = await _resolve(client.app.info())
        assert TOKEN not in repr(client)

    assert result.id == APP["id"]
    assert str(calls[0].url) == expected_url
    assert calls[0].method == "GET"
    assert calls[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert calls[0].extensions["timeout"] == {
        "connect": 30,
        "read": 30,
        "write": 30,
        "pool": 30,
    }


@pytest.mark.parametrize("environment", ["production", "sandbox", "", "MAINNET"])
@pytest.mark.parametrize("client_class", [PayClient, AsyncPayClient])
def test_invalid_environment_rejected(client_class: Any, environment: str) -> None:
    with pytest.raises(ValueError):
        client_class(environment=environment)


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "https://user@example.com",
        "https://user:password@example.com",
        "https://example.com?key=value",
        "https://example.com/#fragment",
        "https://example.com/api/v1",
        "http://example.com",
        "http://localhost.example.com",
        "http://192.168.1.5",
        "ftp://localhost",
        "not-a-url",
        "/relative",
    ],
)
@pytest.mark.parametrize("client_class", [PayClient, AsyncPayClient])
def test_unsafe_base_url_rejected(client_class: Any, base_url: str) -> None:
    with pytest.raises(ValueError):
        client_class(api_token=TOKEN, base_url=base_url)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("client_class", [PayClient, AsyncPayClient])
def test_invalid_timeout_rejected(client_class: Any, timeout: float) -> None:
    with pytest.raises(ValueError):
        client_class(timeout=timeout)


async def test_closing_sdk_blocks_requests_but_preserves_injected_http(backend: str) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=APP)

    async with _sdk(backend, respond, api_token=TOKEN, timeout=12) as (client, http):
        http.headers["x-custom-header"] = "unchanged"
        original_headers = dict(http.headers)
        original_timeout = http.timeout
        original_base_url = http.base_url
        original_follow_redirects = http.follow_redirects
        await _resolve(client.app.info())
        await _close(client)
        await _close(client)
        with pytest.raises(RuntimeError, match="[Cc]losed"):
            await _resolve(client.app.info())

        assert len(calls) == 1
        assert not http.is_closed
        assert dict(http.headers) == original_headers
        assert http.timeout == original_timeout
        assert http.base_url == original_base_url
        assert http.follow_redirects == original_follow_redirects
        assert "authorization" not in http.headers
        assert calls[0].headers["x-custom-header"] == "unchanged"
        assert calls[0].extensions["timeout"]["read"] == 12

        response = await _resolve(http.get("https://still-usable.example/app"))
        assert response.status_code == 200
        assert len(calls) == 2


async def test_context_manager_closes_sdk_without_closing_injected_http(backend: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=APP)

    async with _sdk(backend, respond, api_token=TOKEN) as (client, http):
        if isinstance(client, AsyncPayClient):
            async with client as entered:
                assert entered is client
                await client.app.info()
        else:
            with client as entered:
                assert entered is client
                client.app.info()
        assert not http.is_closed
        with pytest.raises(RuntimeError, match="[Cc]losed"):
            await _resolve(client.app.info())


async def test_owned_http_client_closed_with_sdk(backend: str) -> None:
    client: Client = AsyncPayClient() if backend == "async" else PayClient()
    # Ownership is deliberately the only test that inspects this private boundary.
    http = client._transport._client
    assert not http.is_closed
    await _close(client)
    assert http.is_closed
    with pytest.raises(RuntimeError, match="[Cc]losed"):
        await _resolve(client.currencies.list())


async def test_injected_auth_cannot_override_bearer(backend: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(200, json=APP)

    async with _sdk(backend, respond, api_token=TOKEN) as (client, http):
        auth = httpx.BasicAuth("other", "credentials")
        http.auth = auth
        await _resolve(client.app.info())
        assert http.auth is auth


async def test_public_request_never_inherits_another_product_token(backend: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, json=[])

    async with _sdk(backend, respond) as (client, http):
        http.headers["Authorization"] = "Bearer unrelated-exchange-token"
        await _resolve(client.rates.get())
        assert http.headers["Authorization"] == "Bearer unrelated-exchange-token"


@pytest.mark.parametrize(
    "path",
    [
        "https://other.example/health",
        "//other.example/health",
        "health",
        "/health?token=untrusted",
        "/health#fragment",
        "/health/",
        "/healthcheck",
        "/Health",
        "/api/v1/app-info?token=untrusted",
        "/api/v1/app-info#fragment",
    ],
)
async def test_request_path_guard_rejects_unsafe_or_unlisted_paths(
    backend: str, path: str
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    http_class = httpx.AsyncClient if backend == "async" else httpx.Client
    transport_class = AsyncTransport if backend == "async" else SyncTransport
    http = http_class(transport=httpx.MockTransport(respond))
    transport = transport_class(
        api_token=TOKEN, base_url="https://pay.example", timeout=30, http_client=http
    )
    try:
        with pytest.raises(ValueError, match="SDK request path"):
            await _resolve(transport.get(path, TypeAdapter(dict[str, Any]), authenticated=False))
        assert calls == []
    finally:
        if isinstance(transport, AsyncTransport):
            await transport.aclose()
        else:
            transport.close()
        if isinstance(http, httpx.AsyncClient):
            await http.aclose()
        else:
            http.close()
