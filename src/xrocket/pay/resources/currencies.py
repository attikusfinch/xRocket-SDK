"""Supported crypto and fiat currencies."""

from typing import Literal

from pydantic import TypeAdapter

from xrocket._core.transport import AsyncTransport, SyncTransport
from xrocket.pay.models import Currency

_CURRENCIES = TypeAdapter(list[Currency])
CurrencyKind = Literal["crypto", "fiat"]


class CurrenciesResource:
    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def list(self, *, kind: CurrencyKind | None = None) -> list[Currency]:
        return self._transport.get(
            "/api/v1/currencies",
            _CURRENCIES,
            params=[("kind", kind)] if kind is not None else None,
            authenticated=False,
        )


class AsyncCurrenciesResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(self, *, kind: CurrencyKind | None = None) -> list[Currency]:
        return await self._transport.get(
            "/api/v1/currencies",
            _CURRENCIES,
            params=[("kind", kind)] if kind is not None else None,
            authenticated=False,
        )
