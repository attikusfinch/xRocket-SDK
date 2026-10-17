"""Create Current withdrawal links without opening or following them."""

from pydantic import TypeAdapter

from xrocket._core.transport import AsyncTransport, SyncTransport
from xrocket.pay.models import WithdrawalLink, WithdrawalLinkRequest

_LINK = TypeAdapter(WithdrawalLink)


class WithdrawalLinksResource:
    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def create(self, *, request: WithdrawalLinkRequest) -> WithdrawalLink:
        """Send once and return optional links; a timeout leaves creation unknown."""
        if not isinstance(request, WithdrawalLinkRequest):
            raise TypeError("request must be a WithdrawalLinkRequest")
        return self._transport.request(
            "POST", "/api/v1/withdrawal-link", _LINK, success_statuses=(200,), body=request
        )


class AsyncWithdrawalLinksResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def create(self, *, request: WithdrawalLinkRequest) -> WithdrawalLink:
        """Send once and return optional links; a timeout leaves creation unknown."""
        if not isinstance(request, WithdrawalLinkRequest):
            raise TypeError("request must be a WithdrawalLinkRequest")
        return await self._transport.request(
            "POST", "/api/v1/withdrawal-link", _LINK, success_statuses=(200,), body=request
        )
