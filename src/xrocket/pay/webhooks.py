"""Stateless Current webhook authentication; no JSON decoding or delivery storage."""

import hashlib
import hmac
import re
import time
from collections.abc import Callable, Mapping
from decimal import Decimal

from .errors import (
    WebhookConfigurationError,
    WebhookError,
    WebhookHeaderError,
    WebhookSignatureError,
    WebhookTimestampError,
)

_SIGNING_HEADERS = frozenset({"signature-timestamp", "signature-version", "signature"})


def _signing_headers(headers: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(headers, Mapping):
        raise WebhookHeaderError("Webhook headers must be a mapping of strings")
    selected: dict[str, str] = {}
    for name, value in headers.items():
        if not isinstance(name, str):
            raise WebhookHeaderError("Webhook header names must be strings")
        key = name.lower()
        if key in _SIGNING_HEADERS:
            if key in selected:
                raise WebhookHeaderError("Duplicate webhook signing header")
            if not isinstance(value, str):
                raise WebhookHeaderError("Webhook signing header values must be strings")
            selected[key] = value
    if selected.keys() != _SIGNING_HEADERS:
        raise WebhookHeaderError("Missing webhook signing header")
    return selected


def _secret_bytes(webhook_secret: str | bytes) -> bytes:
    if isinstance(webhook_secret, str):
        # Avoid UnicodeEncodeError retaining an invalid secret in its object/args.
        if any(0xD800 <= ord(char) <= 0xDFFF for char in webhook_secret):
            raise WebhookConfigurationError("Webhook secret must contain Unicode scalar values")
        secret = webhook_secret.encode("utf-8")
    elif isinstance(webhook_secret, bytes):
        secret = webhook_secret
    else:
        raise WebhookConfigurationError("Webhook secret must be str or bytes")
    if not secret:
        raise WebhookConfigurationError("Webhook secret must not be empty")
    return secret


def _current_ms(clock: Callable[[], int] | None) -> int:
    if clock is None:
        return time.time_ns() // 1_000_000
    failed = False
    now: object = None
    try:
        now = clock()
    except Exception:
        failed = True
    # Raise outside the handler: even __context__ must not retain a clock's inputs.
    if failed:
        raise WebhookConfigurationError("Webhook clock failed")
    if type(now) is not int or now < 0:
        raise WebhookConfigurationError(
            "Webhook clock must return nonnegative integer milliseconds"
        )
    return now


def _decimal_key(value: str) -> tuple[int, str]:
    normalized = value.lstrip("0") or "0"
    return len(normalized), normalized


def verify_webhook_signature(
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
    webhook_secret: str | bytes,
    tolerance_ms: int = 300_000,
    clock: Callable[[], int] | None = None,
) -> None:
    """Authenticate exact body bytes and enforce an inclusive +/- time window.

    ``webhook_secret`` is the separate Current webhook secret, never an API JWT.
    Strings use UTF-8 without trimming or hashing; bytes are used as-is. Header names
    are case-insensitive, values are exact. The timestamp must be nonempty ASCII
    decimal milliseconds; leading zeros are permitted and remain signed verbatim.
    Signature-Version must be exactly v1; Signature is 64 hex digits (either case).

    ``tolerance_ms`` is a nonnegative integer, default 300000 ms, applied equally to
    past and future timestamps with inclusive boundaries. Zero requires an exact
    clock match. ``clock`` returns integer Unix milliseconds; None uses system time.
    This is SDK policy, not an upstream clock-skew/retry guarantee. There is no
    deduplication: a valid delivery can pass repeatedly inside the window.

    Success returns None. Failure raises a Pay WebhookError subclass without
    retaining secret/body/header values in exception diagnostics. No JSON parsing,
    network access, JWT lookup, secret storage, or Legacy key transform occurs.
    """
    try:
        _verify_signature_and_time(
            raw_body=raw_body,
            headers=headers,
            webhook_secret=webhook_secret,
            tolerance_ms=tolerance_ms,
            clock=clock,
        )
    except WebhookError as error:
        # A caller may invoke us inside an except block with sensitive context.
        # Clear it before bare re-raise, which preserves the cleared chain.
        error.__context__ = None
        error.__cause__ = None
        raise


def _verify_signature_and_time(
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
    webhook_secret: str | bytes,
    tolerance_ms: int,
    clock: Callable[[], int] | None,
) -> None:
    if not isinstance(raw_body, bytes):
        raise WebhookConfigurationError("Webhook raw_body must be bytes")
    if type(tolerance_ms) is not int or tolerance_ms < 0:
        raise WebhookConfigurationError("Webhook tolerance_ms must be a nonnegative integer")
    secret = _secret_bytes(webhook_secret)
    signing = _signing_headers(headers)
    timestamp = signing["signature-timestamp"]
    if re.fullmatch(r"[0-9]+", timestamp) is None:
        raise WebhookHeaderError("Malformed webhook timestamp")
    if signing["signature-version"] != "v1":
        raise WebhookHeaderError("Unsupported webhook signature version")
    signature = signing["signature"]
    if re.fullmatch(r"[0-9a-fA-F]{64}", signature) is None:
        raise WebhookHeaderError("Malformed webhook signature")

    mac = hmac.new(secret, digestmod=hashlib.sha256)
    mac.update(timestamp.encode("ascii"))
    mac.update(b".")
    mac.update(raw_body)
    if not hmac.compare_digest(mac.digest(), bytes.fromhex(signature)):
        raise WebhookSignatureError("Webhook signature verification failed")

    now_ms = _current_ms(clock)
    # Decimal string comparison avoids integer parsing limits for untrusted headers,
    # while preserving their original bytes above (including any leading zeros).
    # Decimal(int) is exact and independent of context precision; its string
    # conversion also avoids Python's configurable int decimal-digit limit for
    # otherwise valid (large) caller-supplied integer clock/tolerance values.
    lower = _decimal_key(str(Decimal(max(0, now_ms - tolerance_ms))))
    upper = _decimal_key(str(Decimal(now_ms + tolerance_ms)))
    if not lower <= _decimal_key(timestamp) <= upper:
        raise WebhookTimestampError("Webhook timestamp is outside the permitted window")
