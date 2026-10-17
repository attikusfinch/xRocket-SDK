"""xRocket Python SDK: service clients live in their respective namespaces."""

from ._core.errors import (
    APIError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    RequestTimeoutError,
    ResponseValidationError,
    ServerError,
    TransportError,
    XRocketError,
)

__all__ = [
    "APIError",
    "AuthenticationError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "RequestTimeoutError",
    "ResponseValidationError",
    "ServerError",
    "TransportError",
    "XRocketError",
]
