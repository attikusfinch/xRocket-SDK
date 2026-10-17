"""Explicit single-page cheque reads using the Current Pay routes."""

from datetime import datetime
from typing import Literal

from pydantic import TypeAdapter

from xrocket._core.transport import AsyncTransport, Query, SyncTransport
from xrocket.pay.models import Cheque, CursorPage

_CHEQUE = TypeAdapter(Cheque)
_PAGE = TypeAdapter(CursorPage[Cheque])


def _date_param(name: str, value: datetime) -> str:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value.isoformat()


def _list_params(
    from_date: datetime | None,
    to_date: datetime | None,
    target_type: str | None,
    target: str | None,
    state: str | None,
    cursor: str | None,
    limit: int | None,
) -> Query:
    if (target_type is None) != (target is None):
        raise ValueError("target_type and target must be supplied together")
    if target_type is not None and target_type not in (
        "user_id", "telegram_user_id", "telegram_username"
    ):
        raise ValueError("target_type must be user_id, telegram_user_id, or telegram_username")
    if target is not None and (not isinstance(target, str) or len(target) > 100):
        raise ValueError("target must be a string of at most 100 characters")
    if state is not None and state not in ("active", "completed", "draft", "error"):
        raise ValueError("state must be active, completed, draft, or error")
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000
    ):
        raise ValueError("limit must be an integer between 1 and 1000")

    params: Query = []
    for name, value in (("fromDate", from_date), ("toDate", to_date)):
        if value is not None:
            params.append((name, _date_param(name, value)))
    for name, item in (
        ("targetType", target_type),
        ("target", target),
        ("state", state),
        ("cursor", cursor),
        ("limit", limit),
    ):
        if item is not None:
            params.append((name, item))
    return params


def _retrieve_params(cheque_id: str | None, client_cheque_id: str | None) -> Query:
    if cheque_id is None and client_cheque_id is None:
        raise ValueError("cheque_id or client_cheque_id is required")
    params: Query = []
    for name, value in (("chequeId", cheque_id), ("clientChequeId", client_cheque_id)):
        if value is not None:
            if not isinstance(value, str) or not 1 <= len(value) <= 100:
                raise ValueError("Cheque identifiers must contain 1 to 100 characters")
            params.append((name, value))
    return params


class ChequesResource:
    def __init__(self, transport: SyncTransport) -> None:
        self._transport = transport

    def list(
        self,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        target_type: Literal["user_id", "telegram_user_id", "telegram_username"] | None = None,
        target: str | None = None,
        state: Literal["active", "completed", "draft", "error"] | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> CursorPage[Cheque]:
        """Read one page; dates require a timezone and target filters form a pair."""
        return self._transport.get(
            "/api/v1/cheques",
            _PAGE,
            params=_list_params(from_date, to_date, target_type, target, state, cursor, limit),
        )

    def retrieve(
        self,
        *,
        cheque_id: str | None = None,
        client_cheque_id: str | None = None,
    ) -> Cheque:
        """Read a cheque by either identifier, passing both when supplied."""
        return self._transport.get(
            "/api/v1/cheque",
            _CHEQUE,
            params=_retrieve_params(cheque_id, client_cheque_id),
        )


class AsyncChequesResource:
    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def list(
        self,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        target_type: Literal["user_id", "telegram_user_id", "telegram_username"] | None = None,
        target: str | None = None,
        state: Literal["active", "completed", "draft", "error"] | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> CursorPage[Cheque]:
        """Read one page; dates require a timezone and target filters form a pair."""
        return await self._transport.get(
            "/api/v1/cheques",
            _PAGE,
            params=_list_params(from_date, to_date, target_type, target, state, cursor, limit),
        )

    async def retrieve(
        self,
        *,
        cheque_id: str | None = None,
        client_cheque_id: str | None = None,
    ) -> Cheque:
        """Read a cheque by either identifier, passing both when supplied."""
        return await self._transport.get(
            "/api/v1/cheque",
            _CHEQUE,
            params=_retrieve_params(cheque_id, client_cheque_id),
        )
