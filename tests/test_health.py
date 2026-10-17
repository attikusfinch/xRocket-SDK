"""The public health endpoint uses the existing HTTP and response pipeline."""

import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from xrocket import ResponseValidationError, ServerError, pay
from xrocket.pay import AsyncPayClient, Health, HealthComponent, PayClient, models
from xrocket.pay.models.health import Health as ResourceHealth
from xrocket.pay.models.health import HealthComponent as ResourceHealthComponent

HEALTH = {"status": "ok", "info": [], "error": [], "details": []}
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


def test_health_models_are_exported_from_both_public_facades() -> None:
    assert Health is ResourceHealth is models.Health
    assert HealthComponent is ResourceHealthComponent is models.HealthComponent
    assert {"Health", "HealthComponent"} <= set(pay.__all__)
    assert {"Health", "HealthComponent"} <= set(models.__all__)


@pytest.mark.parametrize(
    ("options", "expected_url"),
    [
        ({}, "https://pay.api.xrocket.exchange/health"),
        ({"environment": "testnet"}, "https://pay.api.testnet.xrocket.exchange/health"),
        ({"base_url": "https://custom.example/"}, "https://custom.example/health"),
    ],
)
async def test_health_is_one_anonymous_request_at_the_origin_root(
    backend: str, options: dict[str, str], expected_url: str
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=HEALTH)

    async with _sdk(backend, respond, **options) as (client, _):
        result = await _resolve(client.health.get())

    assert isinstance(result, Health)
    assert result.model_dump() == HEALTH
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert str(calls[0].url) == expected_url
    assert calls[0].headers["accept"] == "application/json"
    assert "authorization" not in calls[0].headers
    assert "Rocket-Pay-Key" not in calls[0].headers


@pytest.mark.parametrize("api_token", [None, "synthetic-pay-token"])
async def test_health_auth_is_isolated_from_the_injected_http_client(
    backend: str, api_token: str | None
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=HEALTH)

    async with _sdk(backend, respond, api_token=api_token) as (client, http):
        auth = httpx.BasicAuth("unrelated", "credentials")
        http.auth = auth
        http.headers["Authorization"] = "Bearer unrelated-exchange-token"
        await _resolve(client.health.get())
        assert http.auth is auth
        assert http.headers["Authorization"] == "Bearer unrelated-exchange-token"

    assert len(calls) == 1
    expected = f"Bearer {api_token}" if api_token is not None else None
    assert calls[0].headers.get("authorization") == expected


async def test_health_keeps_typed_lists_future_statuses_and_fields(backend: str) -> None:
    payload = {
        "status": "maintenance",
        "info": [{"name": "cache", "status": "warming", "cacheHits": 4}],
        "error": [{"name": "database", "status": "down", "message": "Unavailable"}],
        "details": [{"name": "worker", "status": "up", "message": "Ready", "lag": 0}],
        "futureField": {"version": 2},
    }
    async with _sdk(backend, lambda _: httpx.Response(200, json=payload)) as (client, _):
        health = await _resolve(client.health.get())

    assert isinstance(health, Health)
    assert health.status == "maintenance"
    for components in (health.info, health.error, health.details):
        assert isinstance(components, list)
        assert all(isinstance(component, HealthComponent) for component in components)
    assert health.info[0].status == "warming"
    assert health.info[0].message is None
    assert health.info[0].model_extra == {"cacheHits": 4}
    assert health.error[0].message == "Unavailable"
    assert health.details[0].message == "Ready"
    assert health.details[0].model_extra == {"lag": 0}
    assert health.model_extra == {"futureField": {"version": 2}}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"status": "ok", "info": [], "error": []},
        {**HEALTH, "status": 1},
        {**HEALTH, "info": {}},
        {**HEALTH, "error": [{"name": "database"}]},
        {**HEALTH, "details": [{"status": "up"}]},
    ],
)
async def test_health_requires_the_inline_schema_fields(backend: str, payload: Any) -> None:
    async with _sdk(backend, lambda _: httpx.Response(200, json=payload)) as (client, _):
        with pytest.raises(ResponseValidationError):
            await _resolve(client.health.get())


async def test_health_http_failure_uses_the_shared_error_pipeline(backend: str) -> None:
    calls: list[httpx.Request] = []
    problem = {"kind": "service_unavailable", "detail": "Temporary outage"}

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            503, json=problem, headers={"x-request-id": "health-request", "retry-after": "7"}
        )

    async with _sdk(backend, respond) as (client, _):
        with pytest.raises(ServerError) as caught:
            await _resolve(client.health.get())

    assert caught.value.status_code == 503
    assert caught.value.problem == problem
    assert caught.value.request_id == "health-request"
    assert caught.value.retry_after == "7"
    assert len(calls) == 1


async def test_health_obeys_sdk_lifecycle_and_injected_http_ownership(backend: str) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=HEALTH)

    async with _sdk(backend, respond) as (client, http):
        await _resolve(client.health.get())
        await _close(client)
        with pytest.raises(RuntimeError, match="[Cc]losed"):
            await _resolve(client.health.get())
        assert not http.is_closed
        assert len(calls) == 1
