"""Explicit payout reads, single creates and mass creates using Current Pay routes."""

from datetime import datetime

from pydantic import TypeAdapter

from xrocket._core.transport import AsyncTransport, Query, SyncTransport
from xrocket.pay.models import (
    CursorPage,
    MassPayoutCreateRequest,
    MassPayoutResult,
    Payout,
    PayoutCreateRequest,
)

_PAYOUT = TypeAdapter(Payout)
_PAGE = TypeAdapter(CursorPage[Payout])
_MASS_PAYOUT = TypeAdapter(MassPayoutResult)


def _date_param(name: str, value: datetime) -> str:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value.isoformat()


def _list_params(
    from_date: datetime | None,
    to_date: datetime | None,
    cursor: str | None,
    limit: int | None,
) -> Query:
    # This GET declares no limit bounds; do not borrow them from other resources.
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)):
        raise ValueError("limit must be an integer")
    params: Query = []
    for name, value in (("fromDate", from_date), ("toDate", to_date)):
        if value is not None:
            params.append((name, _date_param(name, value)))
    if cursor is not None:
        params.append(("cursor", cursor))
    if limit is not None:
        params.append(("limit", limit))
    return params


def _retrieve_params(payout_id: str | None, client_payout_id: str | None) -> Query:
    if payout_id is None and client_payout_id is None:
        raise ValueError("payout_id or client_payout_id is required")
    params: Query = []
    for name, value in (("payoutId", payout_id), ("clientPayoutId", client_payout_id)):
        if value is not None:
            if not isinstance(value, str) or not 1 <= len(value) <= 100:
                raise ValueError("Payout identifiers must contain 1 to 100 characters")
            params.append((name, value))
    return params


class PayoutsResource:
    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def create(self, *, request: PayoutCreateRequest) -> Payout:
        """Send once; a timeout leaves the payout outcome unknown.

        If supplied, use the saved client ID for an explicit ``retrieve`` after
        a timeout. Duplicate API errors propagate; no retry or lookup is hidden.
        """
        if not isinstance(request, PayoutCreateRequest):
            raise TypeError("request must be a PayoutCreateRequest")
        return self._transport.request(
            "POST", "/api/v1/payouts", _PAYOUT, success_statuses=(200,), body=request
        )

    def create_mass(self, *, request: MassPayoutCreateRequest) -> MassPayoutResult:
        """Send one batch once, returning separate successes and item errors.

        HTTP 200 does not imply every item succeeded. No splitting, lookup or
        replay is automatic; a timeout leaves individual outcomes unknown.
        """
        if not isinstance(request, MassPayoutCreateRequest):
            raise TypeError("request must be a MassPayoutCreateRequest")
        return self._transport.request(
            "POST", "/api/v1/mass-payouts", _MASS_PAYOUT, success_statuses=(200,), body=request
        )

    def list(
        self,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> CursorPage[Payout]:
        """Read one page; date filters require timezone-aware datetime values."""
        return self._transport.get(
            "/api/v1/payouts",
            _PAGE,
            params=_list_params(from_date, to_date, cursor, limit),
        )

    def retrieve(
        self,
        *,
        payout_id: str | None = None,
        client_payout_id: str | None = None,
    ) -> Payout:
        """Read a payout by either identifier, passing both when supplied."""
        return self._transport.get(
            "/api/v1/payout",
            _PAYOUT,
            params=_retrieve_params(payout_id, client_payout_id),
        )


class AsyncPayoutsResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def create(self, *, request: PayoutCreateRequest) -> Payout:
        """Send once; a timeout leaves the payout outcome unknown.

        If supplied, use the saved client ID for an explicit ``retrieve`` after
        a timeout. Duplicate API errors propagate; no retry or lookup is hidden.
        """
        if not isinstance(request, PayoutCreateRequest):
            raise TypeError("request must be a PayoutCreateRequest")
        return await self._transport.request(
            "POST", "/api/v1/payouts", _PAYOUT, success_statuses=(200,), body=request
        )

    async def create_mass(self, *, request: MassPayoutCreateRequest) -> MassPayoutResult:
        """Send one batch once, returning separate successes and item errors.

        HTTP 200 does not imply every item succeeded. No splitting, lookup or
        replay is automatic; a timeout leaves individual outcomes unknown.
        """
        if not isinstance(request, MassPayoutCreateRequest):
            raise TypeError("request must be a MassPayoutCreateRequest")
        return await self._transport.request(
            "POST", "/api/v1/mass-payouts", _MASS_PAYOUT, success_statuses=(200,), body=request
        )

    async def list(
        self,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> CursorPage[Payout]:
        """Read one page; date filters require timezone-aware datetime values."""
        return await self._transport.get(
            "/api/v1/payouts",
            _PAGE,
            params=_list_params(from_date, to_date, cursor, limit),
        )

    async def retrieve(
        self,
        *,
        payout_id: str | None = None,
        client_payout_id: str | None = None,
    ) -> Payout:
        """Read a payout by either identifier, passing both when supplied."""
        return await self._transport.get(
            "/api/v1/payout",
            _PAYOUT,
            params=_retrieve_params(payout_id, client_payout_id),
        )
