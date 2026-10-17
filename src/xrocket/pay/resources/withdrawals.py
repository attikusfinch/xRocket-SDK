"""Explicit withdrawal reads and required network/asset quotas queries."""

from datetime import datetime
from typing import Literal

from pydantic import TypeAdapter

from xrocket._core.transport import AsyncTransport, Query, SyncTransport
from xrocket.pay.models import CursorPage, Withdrawal, WithdrawalQuotas

_WITHDRAWAL = TypeAdapter(Withdrawal)
_PAGE = TypeAdapter(CursorPage[Withdrawal])
_QUOTAS = TypeAdapter(WithdrawalQuotas)


def _date_param(name: str, value: datetime) -> str:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value.isoformat()


def _list_params(
    from_date: datetime | None,
    to_date: datetime | None,
    status: str | None,
    cursor: str | None,
    limit: int | None,
) -> Query:
    if status is not None and status not in ("CREATED", "COMPLETED", "FAIL"):
        raise ValueError("status must be CREATED, COMPLETED, or FAIL")
    # This GET declares no limit bounds; leave range validation to the server.
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)):
        raise ValueError("limit must be an integer")
    params: Query = []
    for name, value in (("fromDate", from_date), ("toDate", to_date)):
        if value is not None:
            params.append((name, _date_param(name, value)))
    if status is not None:
        params.append(("status", status))
    if cursor is not None:
        params.append(("cursor", cursor))
    if limit is not None:
        params.append(("limit", limit))
    return params


def _retrieve_params(withdrawal_id: str | None, client_withdrawal_id: str | None) -> Query:
    # PAY-017: a local SDK guard, not a documented upstream missing-ID contract.
    if withdrawal_id is None and client_withdrawal_id is None:
        raise ValueError("withdrawal_id or client_withdrawal_id is required by the SDK")
    params: Query = []
    for name, value in (
        ("withdrawalId", withdrawal_id), ("clientWithdrawalId", client_withdrawal_id)
    ):
        if value is not None:
            if not isinstance(value, str) or not 1 <= len(value) <= 100:
                raise ValueError("Withdrawal GET identifiers must contain 1 to 100 characters")
            params.append((name, value))
    return params


def _quotas_params(network: str, asset: str) -> Query:
    if network not in ("TON", "BSC", "ETH", "BTC", "TRX", "SOL"):
        raise ValueError("network must be TON, BSC, ETH, BTC, TRX, or SOL")
    if not isinstance(asset, str):
        raise ValueError("asset must be a string")
    return [("network", network), ("asset", asset)]


class WithdrawalsResource:
    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def list(
        self,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        status: Literal["CREATED", "COMPLETED", "FAIL"] | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> CursorPage[Withdrawal]:
        """Read one page; date filters require timezone-aware datetime values."""
        return self._transport.get(
            "/api/v1/withdrawals",
            _PAGE,
            params=_list_params(from_date, to_date, status, cursor, limit),
        )

    def retrieve(
        self,
        *,
        withdrawal_id: str | None = None,
        client_withdrawal_id: str | None = None,
    ) -> Withdrawal:
        """Require an identifier locally; upstream missing-ID behavior is unconfirmed."""
        return self._transport.get(
            "/api/v1/withdrawal",
            _WITHDRAWAL,
            params=_retrieve_params(withdrawal_id, client_withdrawal_id),
        )

    def quotas(
        self,
        *,
        network: Literal["TON", "BSC", "ETH", "BTC", "TRX", "SOL"],
        asset: str,
    ) -> WithdrawalQuotas:
        """Read quotas for a required network and asset pair."""
        return self._transport.get(
            "/api/v1/withdrawal-quotas", _QUOTAS, params=_quotas_params(network, asset)
        )


class AsyncWithdrawalsResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(
        self,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        status: Literal["CREATED", "COMPLETED", "FAIL"] | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> CursorPage[Withdrawal]:
        """Read one page; date filters require timezone-aware datetime values."""
        return await self._transport.get(
            "/api/v1/withdrawals",
            _PAGE,
            params=_list_params(from_date, to_date, status, cursor, limit),
        )

    async def retrieve(
        self,
        *,
        withdrawal_id: str | None = None,
        client_withdrawal_id: str | None = None,
    ) -> Withdrawal:
        """Require an identifier locally; upstream missing-ID behavior is unconfirmed."""
        return await self._transport.get(
            "/api/v1/withdrawal",
            _WITHDRAWAL,
            params=_retrieve_params(withdrawal_id, client_withdrawal_id),
        )

    async def quotas(
        self,
        *,
        network: Literal["TON", "BSC", "ETH", "BTC", "TRX", "SOL"],
        asset: str,
    ) -> WithdrawalQuotas:
        """Read quotas for a required network and asset pair."""
        return await self._transport.get(
            "/api/v1/withdrawal-quotas", _QUOTAS, params=_quotas_params(network, asset)
        )
