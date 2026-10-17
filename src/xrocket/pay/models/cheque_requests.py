"""Intentional Current Pay cheque inputs, separate from response records."""

from typing import Any, Literal, Self, cast

from pydantic import (
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    SecretStr,
    SerializationInfo,
    ValidationError,
    field_serializer,
    model_validator,
)
from pydantic.alias_generators import to_camel
from pydantic_core import InitErrorDetails

from ..._core.serialization import RequestModel, RequestMoney


class _ChequeRequestModel(RequestModel):
    model_config = ConfigDict(alias_generator=to_camel, strict=True, hide_input_in_errors=True)

    def _validate_request(self) -> None:
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} must be omitted instead of set to None")

    @model_validator(mode="after")
    def _request_policies(self) -> Self:
        self._validate_request()
        return self

    @model_validator(mode="wrap")
    @classmethod
    def _safe_validation(cls, value: Any, handler: ModelWrapValidatorHandler[Self]) -> Self:
        try:
            return handler(value)
        except ValidationError as error:
            # Model-level and sibling errors can otherwise include the whole
            # input dict, including a password that has not been wrapped yet.
            details = cast(list[InitErrorDetails], error.errors(include_input=False))
            raise ValidationError.from_exception_data(
                cls.__name__, details, hide_input=True
            ) from None


class ChequeCallbackRequest(_ChequeRequestModel):
    """Optional cheque webhook override and caller-supplied JSON object."""

    callback_url: str | None = Field(default=None, max_length=500)
    payload: dict[str, Any] | None = None


class ChequeURLRequest(_ChequeRequestModel):
    """Optional redirects after cheque activation or cancellation."""

    success_url: str | None = Field(default=None, max_length=500)
    cancel_url: str | None = Field(default=None, max_length=500)


class ChequeCreateRequest(_ChequeRequestModel):
    """Create input with exact money and an optional addressed recipient.

    Passwords are masked in normal model dumps and representations. The request
    serializer reveals the password only while preparing outbound JSON bytes.
    """

    asset: str
    amount: RequestMoney
    client_cheque_id: str | None = Field(default=None, max_length=50)
    password: SecretStr | None = Field(default=None, max_length=100, repr=False)
    description: str | None = Field(default=None, max_length=1000)
    callback: ChequeCallbackRequest | None = None
    url: ChequeURLRequest | None = None
    target_type: Literal["user_id", "telegram_user_id", "telegram_username"] | None = None
    target: str | None = Field(default=None, max_length=100)

    @field_serializer("password")
    def _password_value(
        self, value: SecretStr | str | None, info: SerializationInfo
    ) -> SecretStr | str | None:
        if value is None:
            return None
        if info.mode == "python":
            return value if isinstance(value, SecretStr) else SecretStr(value)
        if isinstance(info.context, dict) and info.context.get("request_wire") is True:
            if not isinstance(value, SecretStr):
                raise ValueError("Password must be validated before wire serialization")
            return value.get_secret_value()
        # Keep ordinary JSON dumps safe even for deliberately bypassed model
        # validation (model_construct/model_copy or a later field assignment).
        return "**********"

    def _validate_request(self) -> None:
        super()._validate_request()
        if (self.target_type is None) != (self.target is None):
            raise ValueError("target_type and target must be supplied together")


class ChequeUpdateRequest(_ChequeRequestModel):
    """Only description can change; omit to leave it alone or use '' to clear."""

    description: str | None = Field(default=None, max_length=1000)
