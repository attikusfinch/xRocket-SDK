"""Offline contract for the shared HTTP mutation pipeline."""

import inspect
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, Field, TypeAdapter

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
)
from xrocket._core.serialization import RequestModel, RequestMoney
from xrocket._core.transport import AsyncTransport, SyncTransport

TOKEN = "synthetic-write-transport-token"
ORIGIN = "https://pay.example"
PATH = "/api/v1/synthetic-write"
ADAPTER = TypeAdapter(dict[str, str])
Transport = SyncTransport | AsyncTransport
HttpClient = httpx.Client | httpx.AsyncClient
Handler = Callable[[httpx.Request], httpx.Response]


class WriteBody(RequestModel):
    amount: RequestMoney
    client_reference: str = Field(alias="clientReference")
    note: str | None = None


class NullableBody(RequestModel):
    note: str | None = None


class ResponseOnly(BaseModel):
    id: str


@pytest.fixture(params=("sync", "async"))
def backend(request: pytest.FixtureRequest) -> str:
    return str(request.param)


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def _close(transport: Transport) -> None:
    if isinstance(transport, AsyncTransport):
        await transport.aclose()
    else:
        transport.close()


@asynccontextmanager
async def _transport(
    backend: str,
    handler: Handler,
    *,
    api_token: str | None = TOKEN,
    **http_options: Any,
) -> AsyncIterator[tuple[Transport, HttpClient]]:
    mock = httpx.MockTransport(handler)
    if backend == "async":
        http: HttpClient = httpx.AsyncClient(transport=mock, **http_options)
        transport: Transport = AsyncTransport(
            api_token=api_token, base_url=ORIGIN, timeout=12, http_client=http
        )
    else:
        http = httpx.Client(transport=mock, **http_options)
        transport = SyncTransport(
            api_token=api_token, base_url=ORIGIN, timeout=12, http_client=http
        )
    try:
        yield transport, http
    finally:
        await _close(transport)
        if isinstance(http, httpx.AsyncClient):
            await http.aclose()
        else:
            http.close()


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
@pytest.mark.parametrize("status", [200, 201])
async def test_write_sends_exact_json_aliases_money_and_literal_query(
    backend: str, method: str, status: int
) -> None:
    calls: list[httpx.Request] = []
    amount = Decimal("12345678901234567890.1234567890123456789000")
    body = WriteBody(amount=amount, clientReference="подарок 🎁")
    cursor = "a+/= &?%#ю"

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={"id": "created"})

    async with _transport(backend, respond) as (transport, _):
        result = await _resolve(
            transport.request(
                method,
                PATH,
                ADAPTER,
                success_statuses=(status,),
                body=body,
                params=[("clientInvoiceId", "synthetic-id"), ("cursor", cursor), ("limit", 2)],
            )
        )

    assert result == {"id": "created"}
    assert len(calls) == 1
    request = calls[0]
    assert request.method == method
    assert request.url.host == "pay.example"
    assert request.url.path == PATH
    assert request.url.params.multi_items() == [
        ("clientInvoiceId", "synthetic-id"),
        ("cursor", cursor),
        ("limit", "2"),
    ]
    assert json.loads(request.content.decode("utf-8")) == {
        "amount": str(amount),
        "clientReference": "подарок 🎁",
    }
    assert request.headers["content-type"] == "application/json"
    assert request.headers["accept"] == "application/json"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert "idempotency-key" not in request.headers
    assert "x-idempotency-key" not in request.headers
    assert body.amount == amount
    assert body.model_fields_set == {"amount", "client_reference"}


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
@pytest.mark.parametrize("status", [200, 201, 204])
async def test_explicit_bodyless_success_returns_none(
    backend: str, method: str, status: int
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status)

    async with _transport(backend, respond) as (transport, _):
        result = await _resolve(transport.request(method, PATH, None, success_statuses=(status,)))

    assert result is None
    assert len(calls) == 1
    assert calls[0].content == b""
    assert "content-type" not in calls[0].headers


@pytest.mark.parametrize(
    ("body", "expected"),
    [(None, b""), (NullableBody(), b"{}"), (NullableBody(note=None), b'{"note":null}')],
)
async def test_absent_body_missing_field_and_explicit_null_remain_distinct(
    backend: str, body: RequestModel | None, expected: bytes
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(204)

    async with _transport(backend, respond) as (transport, _):
        await _resolve(transport.request("PUT", PATH, None, success_statuses=(204,), body=body))

    assert calls[0].content == expected
    assert ("content-type" in calls[0].headers) is (body is not None)


@pytest.mark.parametrize("body", [b"{}", b"null", b"[]", b" ", b"\n", b"not JSON"])
async def test_bodyless_policy_rejects_every_nonempty_response(backend: str, body: bytes) -> None:
    async with _transport(backend, lambda request: httpx.Response(200, content=body)) as (
        transport,
        _,
    ):
        with pytest.raises(ResponseValidationError):
            await _resolve(transport.request("DELETE", PATH, None, success_statuses=(200,)))


@pytest.mark.parametrize("body", [b"", b"[", b"null", b"{}", b'{"id":1}', b"<html/>"])
async def test_typed_policy_requires_json_matching_adapter(backend: str, body: bytes) -> None:
    # An empty mapping is valid for a dict adapter, so use a required-field model.
    adapter = TypeAdapter(ResponseOnly)
    async with _transport(backend, lambda request: httpx.Response(200, content=body)) as (
        transport,
        _,
    ):
        with pytest.raises(ResponseValidationError):
            await _resolve(transport.request("POST", PATH, adapter, success_statuses=(200,)))


@pytest.mark.parametrize("status", [200, 201, 202, 204, 206, 299])
async def test_unexpected_2xx_is_response_validation_error(backend: str, status: int) -> None:
    expected = (201,) if status != 201 else (200,)
    async with _transport(
        backend, lambda request: httpx.Response(status, json={"id": "created"})
    ) as (transport, _):
        with pytest.raises(ResponseValidationError):
            await _resolve(transport.request("POST", PATH, ADAPTER, success_statuses=expected))


async def test_success_policy_can_explicitly_allow_multiple_statuses(backend: str) -> None:
    responses = iter([httpx.Response(200, json={"id": "a"}), httpx.Response(201, json={"id": "b"})])
    async with _transport(backend, lambda request: next(responses)) as (transport, _):
        first = await _resolve(
            transport.request("POST", PATH, ADAPTER, success_statuses=(200, 201))
        )
        second = await _resolve(
            transport.request("POST", PATH, ADAPTER, success_statuses=(200, 201))
        )
    assert first == {"id": "a"}
    assert second == {"id": "b"}


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, APIError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (429, RateLimitError),
        (500, ServerError),
    ],
)
async def test_write_errors_preserve_problem_metadata_without_retry(
    backend: str, status: int, error_type: type[APIError]
) -> None:
    calls: list[httpx.Request] = []
    problem = {"type": "/api/problems/synthetic", "detail": TOKEN}

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            json=problem,
            headers={"x-request-id": "write-request", "retry-after": "9"},
        )

    async with _transport(backend, respond) as (transport, _):
        with pytest.raises(error_type) as caught:
            await _resolve(
                transport.request("POST", PATH, None, success_statuses=(204,), body=NullableBody())
            )

    assert type(caught.value) is error_type
    assert caught.value.status_code == status
    assert caught.value.problem == problem
    assert caught.value.request_id == "write-request"
    assert caught.value.retry_after == "9"
    assert TOKEN not in str(caught.value)
    assert TOKEN not in repr(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [301, 302, 307, 308])
async def test_write_redirect_never_replays_body_or_follows_http_default(
    backend: str, status: int
) -> None:
    calls: list[httpx.Request] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, headers={"location": "https://other.invalid/sink"})

    async with _transport(backend, redirect, follow_redirects=True) as (transport, http):
        with pytest.raises(APIError) as caught:
            await _resolve(
                transport.request("POST", PATH, None, success_statuses=(204,), body=NullableBody())
            )
        assert http.follow_redirects is True

    assert caught.value.status_code == status
    assert len(calls) == 1
    assert calls[0].url.host == "pay.example"


@pytest.mark.parametrize(
    ("failure_type", "error_type"),
    [
        (httpx.WriteTimeout, RequestTimeoutError),
        (httpx.PoolTimeout, RequestTimeoutError),
        (httpx.WriteError, TransportError),
        (httpx.ConnectError, TransportError),
    ],
)
async def test_write_network_failure_is_single_attempt(
    backend: str,
    failure_type: type[httpx.RequestError],
    error_type: type[TransportError],
) -> None:
    calls: list[httpx.Request] = []

    def fail(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise failure_type(f"synthetic failure {TOKEN}", request=request)

    async with _transport(backend, fail) as (transport, _):
        with pytest.raises(error_type) as caught:
            await _resolve(
                transport.request(
                    "POST", PATH, ADAPTER, success_statuses=(200,), body=NullableBody()
                )
            )

    assert type(caught.value) is error_type
    assert TOKEN not in str(caught.value)
    assert TOKEN not in repr(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("api_token", [None, TOKEN])
async def test_writes_isolate_auth_and_override_timeout_without_mutating_injected_client(
    backend: str, api_token: str | None
) -> None:
    calls: list[httpx.Request] = []
    auth = httpx.BasicAuth("other", "synthetic-password")

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"id": "updated"})

    async with _transport(
        backend,
        respond,
        api_token=api_token,
        auth=auth,
        headers={"Authorization": "Bearer unrelated-exchange-token", "X-Custom": "retained"},
        timeout=77,
        base_url="https://unrelated.invalid",
        follow_redirects=True,
    ) as (transport, http):
        original_headers = dict(http.headers)
        original_timeout = http.timeout
        original_base_url = http.base_url
        for _ in range(2):
            result = await _resolve(
                transport.request(
                    "PUT",
                    PATH,
                    ADAPTER,
                    success_statuses=(200,),
                    body=NullableBody(note=None),
                    authenticated=False,
                )
            )
            assert result == {"id": "updated"}
        await _close(transport)
        await _close(transport)
        with pytest.raises(RuntimeError, match="[Cc]losed"):
            await _resolve(transport.request("DELETE", PATH, None, success_statuses=(200,)))
        assert not http.is_closed
        assert dict(http.headers) == original_headers
        assert http.timeout == original_timeout
        assert http.base_url == original_base_url
        assert http.follow_redirects is True
        assert http.auth is auth
        assert transport._client is http

    assert len(calls) == 2
    for request in calls:
        assert str(request.url) == ORIGIN + PATH
        assert request.headers["x-custom"] == "retained"
        if api_token is None:
            assert "authorization" not in request.headers
        else:
            assert request.headers["authorization"] == f"Bearer {api_token}"
        assert request.extensions["timeout"] == {
            "connect": 12,
            "read": 12,
            "write": 12,
            "pool": 12,
        }


@pytest.mark.parametrize("body", [None, NullableBody(note="ёж 🎁")])
async def test_write_framing_describes_actual_utf8_bytes_despite_injected_defaults(
    backend: str, body: RequestModel | None
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(204)

    defaults = {
        "Content-Type": "text/plain",
        "Content-Length": "999",
        "Transfer-Encoding": "chunked",
        "Content-Encoding": "gzip",
    }
    async with _transport(backend, respond, headers=defaults) as (transport, http):
        original_headers = dict(http.headers)
        await _resolve(transport.request("POST", PATH, None, success_statuses=(204,), body=body))
        assert dict(http.headers) == original_headers

    request = calls[0]
    expected = b"" if body is None else '{"note":"ёж 🎁"}'.encode()
    assert request.content == expected
    assert int(request.headers["content-length"]) == len(expected)
    assert "transfer-encoding" not in request.headers
    assert "content-encoding" not in request.headers
    if body is not None:
        assert request.headers["content-type"] == "application/json"


async def test_private_write_requires_sdk_token_before_io(backend: str) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"id": "created"})

    async with _transport(backend, respond, api_token=None) as (transport, _):
        with pytest.raises(AuthenticationError):
            await _resolve(transport.request("POST", PATH, ADAPTER, success_statuses=(200,)))
    assert calls == []


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/health/",
        "/api",
        "api/v1/item",
        "https://other.invalid/api/item",
        "//other.invalid/api/item",
        "/api/v1/item?token=unsafe",
        "/api/v1/item#fragment",
    ],
)
async def test_write_path_guard_runs_before_io(backend: str, method: str, path: str) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(204)

    async with _transport(backend, respond) as (transport, _):
        with pytest.raises(ValueError):
            await _resolve(transport.request(method, path, None, success_statuses=(204,)))
    assert calls == []


@pytest.mark.parametrize("method", ["post", "Post", "put", "delete", "PATCH", "HEAD", "", None])
async def test_unsupported_or_inexact_method_rejected_before_io(backend: str, method: Any) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(204)

    async with _transport(backend, respond) as (transport, _):
        with pytest.raises(ValueError):
            await _resolve(transport.request(method, PATH, None, success_statuses=(204,)))
    assert calls == []


@pytest.mark.parametrize(
    "statuses",
    [(), (True,), (False,), ("200",), (200.0,), (199,), (300,), (400,), (200, 500), [200], None],
)
async def test_invalid_success_policy_rejected_before_io(backend: str, statuses: Any) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"id": "created"})

    async with _transport(backend, respond) as (transport, _):
        with pytest.raises(ValueError):
            await _resolve(transport.request("POST", PATH, ADAPTER, success_statuses=statuses))
    assert calls == []


async def test_success_policy_is_required_before_io(backend: str) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"id": "created"})

    async with _transport(backend, respond) as (transport, _):
        with pytest.raises(TypeError):
            await _resolve(transport.request("POST", PATH, ADAPTER))
    assert calls == []


@pytest.mark.parametrize(
    "body", [{"id": "response-extra"}, ResponseOnly(id="response"), [], "null"]
)
async def test_only_request_models_can_be_serialized_before_io(backend: str, body: Any) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"id": "created"})

    async with _transport(backend, respond) as (transport, _):
        with pytest.raises((TypeError, ValueError)):
            await _resolve(
                transport.request("POST", PATH, ADAPTER, success_statuses=(200,), body=body)
            )
    assert calls == []


@pytest.mark.parametrize("amount", [0.1, True, Decimal("NaN"), "Infinity"])
async def test_bypassed_request_validation_still_rejects_invalid_money_before_io(
    backend: str, amount: Any
) -> None:
    calls: list[httpx.Request] = []
    body = WriteBody.model_construct(amount=amount, client_reference="synthetic-id")

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"id": "created"})

    async with _transport(backend, respond) as (transport, _):
        with pytest.raises(ValueError):
            await _resolve(
                transport.request("POST", PATH, ADAPTER, success_statuses=(200,), body=body)
            )
    assert calls == []


async def test_typed_json_null_is_distinct_from_bodyless_policy(backend: str) -> None:
    async with _transport(backend, lambda request: httpx.Response(200, content=b"null")) as (
        transport,
        _,
    ):
        result = await _resolve(
            transport.request("POST", PATH, TypeAdapter(str | None), success_statuses=(200,))
        )
    assert result is None


@pytest.mark.parametrize("adapter", [dict, {}, "empty"])
async def test_adapter_policy_is_validated_before_io(backend: str, adapter: Any) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    async with _transport(backend, respond) as (transport, _):
        with pytest.raises(TypeError):
            await _resolve(transport.request("POST", PATH, adapter, success_statuses=(200,)))
    assert calls == []


async def test_get_request_with_body_is_rejected_before_io(backend: str) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"id": "created"})

    async with _transport(backend, respond) as (transport, _):
        with pytest.raises(ValueError):
            await _resolve(
                transport.request(
                    "GET", PATH, ADAPTER, success_statuses=(200,), body=NullableBody()
                )
            )
    assert calls == []
