"""Application identity and balances."""

from pydantic import TypeAdapter

from xrocket._core.transport import AsyncTransport, SyncTransport
from xrocket.pay.models import AppBalances, AppInfo

_INFO = TypeAdapter(AppInfo)
_BALANCES = TypeAdapter(AppBalances)


class AppResource:
    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def info(self) -> AppInfo:
        return self._transport.get("/api/v1/app-info", _INFO)

    def balances(self) -> AppBalances:
        return self._transport.get("/api/v1/balances", _BALANCES)


class AsyncAppResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def info(self) -> AppInfo:
        return await self._transport.get("/api/v1/app-info", _INFO)

    async def balances(self) -> AppBalances:
        return await self._transport.get("/api/v1/balances", _BALANCES)
