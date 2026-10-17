"""Exchange rates, with optional authentication in Current Pay."""

from pydantic import TypeAdapter

from xrocket._core.transport import AsyncTransport, Query, SyncTransport
from xrocket.pay.models import Rate

_RATES = TypeAdapter(list[Rate])


def _params(base: str | None, assets: list[str] | None) -> Query:
    params: Query = [("base", base)] if base is not None else []
    if assets is not None:
        params.extend(("assets", asset) for asset in assets)
    return params


class RatesResource:
    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def get(self, *, base: str | None = None, assets: list[str] | None = None) -> list[Rate]:
        return self._transport.get(
            "/api/v1/rates",
            _RATES,
            params=_params(base, assets),
            authenticated=False,
        )


class AsyncRatesResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def get(self, *, base: str | None = None, assets: list[str] | None = None) -> list[Rate]:
        return await self._transport.get(
            "/api/v1/rates",
            _RATES,
            params=_params(base, assets),
            authenticated=False,
        )
