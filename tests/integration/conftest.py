"""Runtime opt-in and testnet-only clients shared by the live GET checks."""

import inspect
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from typing import Any, Literal

import pytest
from pydantic import SecretStr

from xrocket.pay import AsyncPayClient, PayClient

Client = PayClient | AsyncPayClient
Backend = Literal["sync", "async"]
IdentifierKind = Literal["server_id", "client_id"]
LiveCall = Callable[..., Awaitable[Any]]


def _require_live() -> None:
    if os.getenv("XROCKET_RUN_LIVE") != "1":
        pytest.skip("Set XROCKET_RUN_LIVE=1 to enable read-only testnet GET checks")


def _testnet_token() -> SecretStr:
    if not os.getenv("XROCKET_PAY_TESTNET_TOKEN"):
        pytest.skip("Set XROCKET_PAY_TESTNET_TOKEN for private testnet GET checks")
    return SecretStr(os.environ["XROCKET_PAY_TESTNET_TOKEN"])


def _identifier_kwargs(resource: str, kind: IdentifierKind) -> dict[str, str]:
    prefix = "CLIENT_" if kind == "client_id" else ""
    variable = f"XROCKET_PAY_TESTNET_{prefix}{resource.upper()}_ID"
    if not os.getenv(variable):
        pytest.skip(f"Set {variable} for this testnet identifier check")
    parameter = f"client_{resource}_id" if kind == "client_id" else f"{resource}_id"
    return {parameter: os.environ[variable]}


def _quotas_kwargs() -> dict[str, str]:
    variables = {
        "network": "XROCKET_PAY_TESTNET_QUOTAS_NETWORK",
        "asset": "XROCKET_PAY_TESTNET_QUOTAS_ASSET",
    }
    missing = [variable for variable in variables.values() if not os.getenv(variable)]
    if missing:
        pytest.skip(f"Set {', '.join(missing)} for the testnet quotas check")
    return {parameter: os.environ[variable] for parameter, variable in variables.items()}


@asynccontextmanager
async def _client(backend: Backend, token: SecretStr | None = None) -> AsyncIterator[Client]:
    if backend == "sync":
        with PayClient(
            api_token=token.get_secret_value() if token is not None else None,
            environment="testnet",
            timeout=15,
        ) as pay:
            yield pay
    else:
        async with AsyncPayClient(
            api_token=token.get_secret_value() if token is not None else None,
            environment="testnet",
            timeout=15,
        ) as pay:
            yield pay


async def _call_live(method: Callable[..., Any], **kwargs: Any) -> Any:
    result = method(**kwargs)
    return await result if inspect.isawaitable(result) else result


async def _call_private(
    method: Callable[..., Any],
    *,
    identifier_resource: str | None = None,
    identifier_kind: IdentifierKind = "server_id",
    quotas: bool = False,
    **kwargs: Any,
) -> Any:
    if identifier_resource is not None:
        kwargs.update(_identifier_kwargs(identifier_resource, identifier_kind))
    if quotas:
        kwargs.update(_quotas_kwargs())
    try:
        return await _call_live(method, **kwargs)
    except Exception:
        # API errors and transport failures must fail without exposing private
        # problem details, IDs, request URLs, or response data in the report.
        pytest.fail(
            "Private testnet GET failed; inspect API/configuration privately", pytrace=False
        )


@pytest.fixture(autouse=True)
def quiet_live_logs() -> Iterator[None]:
    """Prevent HTTPX/HTTPcore request logging from exposing private query IDs."""
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


@pytest.fixture(params=["sync", "async"], ids=["sync", "async"])
def live_backend(request: pytest.FixtureRequest) -> Backend:
    return request.param


@pytest.fixture(params=["server_id", "client_id"], ids=["server_id", "client_id"])
def identifier_kind(request: pytest.FixtureRequest) -> IdentifierKind:
    return request.param


@pytest.fixture
async def public_pay(live_backend: Backend) -> AsyncIterator[Client]:
    _require_live()
    async with _client(live_backend) as pay:
        yield pay


@pytest.fixture
async def private_pay(live_backend: Backend) -> AsyncIterator[Client]:
    _require_live()
    try:
        async with _client(live_backend, _testnet_token()) as pay:
            yield pay
    except Exception:
        pytest.fail("Private testnet client setup or cleanup failed", pytrace=False)


@pytest.fixture
def live_call() -> LiveCall:
    return _call_live


@pytest.fixture
def private_live_call() -> LiveCall:
    return _call_private
