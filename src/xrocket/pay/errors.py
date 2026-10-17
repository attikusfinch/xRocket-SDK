"""Pay webhook failures, independent of HTTP/API authentication errors."""

from xrocket._core.errors import XRocketError


class WebhookError(XRocketError):
    """Base for webhook failures; diagnostics do not retain request inputs."""


class WebhookConfigurationError(WebhookError):
    """Invalid verifier inputs or local clock configuration."""


class WebhookHeaderError(WebhookError):
    """A required signing header is missing, duplicated, or malformed."""


class WebhookSignatureError(WebhookError):
    """The Current signature does not authenticate the supplied bytes."""


class WebhookTimestampError(WebhookError):
    """An authenticated delivery is outside the configured time window."""


class WebhookPayloadError(WebhookError):
    """Authenticated bytes contain invalid JSON or a malformed Current payload."""
