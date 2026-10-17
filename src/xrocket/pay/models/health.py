"""Public service health and its component results."""

from ._base import _ResponseModel


class HealthComponent(_ResponseModel):
    name: str
    status: str
    message: str | None = None


class Health(_ResponseModel):
    status: str
    info: list[HealthComponent]
    error: list[HealthComponent]
    details: list[HealthComponent]
