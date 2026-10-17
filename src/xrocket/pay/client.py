"""Sync and async entry points for the Current Pay REST API."""

from types import TracebackType
from typing import Self

import httpx

from xrocket._core.transport import AsyncTransport, Environment, SyncTransport
from xrocket.pay.resources.app import AppResource, AsyncAppResource
from xrocket.pay.resources.currencies import AsyncCurrenciesResource, CurrenciesResource
from xrocket.pay.resources.invoices import AsyncInvoicesResource, InvoicesResource
from xrocket.pay.resources.rates import AsyncRatesResource, RatesResource

_BASE_URLS: dict[Environment, str] = {
    "mainnet": "https://pay.api.xrocket.exchange",
    "testnet": "https://pay.api.testnet.xrocket.exchange",
}


def _resolve_url(environment: Environment, base_url: str | None) -> str:
    if environment not in _BASE_URLS:
        raise ValueError("environment must be 'mainnet' or 'testnet'")
    return base_url if base_url is not None else _BASE_URLS[environment]


class PayClient:
    """Current Pay client. Injected HTTP clients remain owned by the caller."""

    def __init__(
        self,
        *,
        api_token: str | None = None,
        environment: Environment = "mainnet",
        base_url: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._transport = SyncTransport(
            api_token=api_token,
            base_url=_resolve_url(environment, base_url),
            timeout=timeout,
            http_client=http_client,
        )
        self.app = AppResource(self._transport)
        self.currencies = CurrenciesResource(self._transport)
        self.rates = RatesResource(self._transport)
        self.invoices = InvoicesResource(self._transport)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class AsyncPayClient:
    """Async Current Pay client with the same resources and caller ownership rules."""

    def __init__(
        self,
        *,
        api_token: str | None = None,
        environment: Environment = "mainnet",
        base_url: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._transport = AsyncTransport(
            api_token=api_token,
            base_url=_resolve_url(environment, base_url),
            timeout=timeout,
            http_client=http_client,
        )
        self.app = AsyncAppResource(self._transport)
        self.currencies = AsyncCurrenciesResource(self._transport)
        self.rates = AsyncRatesResource(self._transport)
        self.invoices = AsyncInvoicesResource(self._transport)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
