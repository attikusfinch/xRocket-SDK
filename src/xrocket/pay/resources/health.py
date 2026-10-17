"""Public service health outside the API version prefix."""

from pydantic import TypeAdapter

from xrocket._core.transport import AsyncTransport, SyncTransport
from xrocket.pay.models import Health

_HEALTH = TypeAdapter(Health)


class HealthResource:
    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def get(self) -> Health:
        return self._transport.get("/health", _HEALTH, authenticated=False)


class AsyncHealthResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def get(self) -> Health:
        return await self._transport.get("/health", _HEALTH, authenticated=False)
