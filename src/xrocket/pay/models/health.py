"""Public service health and its component results."""

from pydantic import field_validator

from ._base import _ResponseModel


class HealthComponent(_ResponseModel):
    name: str
    status: str
    message: str | None = None


class Health(_ResponseModel):
    status: str
    info: list[HealthComponent] | None = None
    error: list[HealthComponent] | None = None
    details: list[HealthComponent] | None = None

    @field_validator("info", "error", "details")
    @classmethod
    def _present_components(cls, value: list[HealthComponent] | None) -> list[HealthComponent]:
        # PAY-018 confirms omission, not nullability. Unvalidated defaults stay
        # None (unknown); a supplied field must retain the OAS list contract.
        if value is None:
            raise ValueError("Present health components must be a list, not null")
        return value
