"""Pay cursor pagination; each resource call returns a single page."""

from typing import Generic, TypeVar

from ._base import _ResponseModel


class CursorPagination(_ResponseModel):
    next: str | None
    total: int | None = None


T = TypeVar("T")


class CursorPage(_ResponseModel, Generic[T]):
    items: list[T]
    pagination: CursorPagination
