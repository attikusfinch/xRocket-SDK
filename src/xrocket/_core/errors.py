"""Stable exceptions shared by xRocket service clients."""

from typing import Any


class XRocketError(Exception):
    """Base exception for SDK failures."""


class APIError(XRocketError):
    """An unsuccessful API response; raw problem details are available explicitly."""

    def __init__(
        self,
        *,
        status_code: int | None = None,
        problem: dict[str, Any] | None = None,
        request_id: str | None = None,
        retry_after: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.problem = problem or {}
        self.request_id = request_id
        self.retry_after = retry_after
        message = (
            f"xRocket API returned HTTP {status_code}" if status_code else "API token required"
        )
        super().__init__(message)


class AuthenticationError(APIError):
    """Authentication is missing or invalid."""


class PermissionDeniedError(APIError):
    """The token is not permitted to perform this request."""


class NotFoundError(APIError):
    """The requested resource does not exist."""


class RateLimitError(APIError):
    """The API rejected the request because of its rate limit."""


class ServerError(APIError):
    """The API returned a server error."""


class TransportError(XRocketError):
    """The HTTP request could not be completed."""


class RequestTimeoutError(TransportError):
    """The HTTP request exceeded its timeout."""


class ResponseValidationError(XRocketError):
    """A successful response did not match the documented response shape."""
