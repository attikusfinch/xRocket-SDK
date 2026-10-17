"""Stateless Current webhook authentication and verified event decoding."""

import hashlib
import hmac
import json
import re
import time
from collections.abc import Callable, Mapping
from copy import deepcopy
from decimal import Decimal
from typing import Any

from .errors import (
    WebhookConfigurationError,
    WebhookError,
    WebhookHeaderError,
    WebhookPayloadError,
    WebhookSignatureError,
    WebhookTimestampError,
)
from .models.webhooks import (
    ChequeWebhook,
    InvoiceWebhook,
    PayoutWebhook,
    UnknownWebhook,
    WebhookEvent,
    WithdrawalWebhook,
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


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> Any:
    raise ValueError("Nonfinite JSON constant")


def _decode_verified_body(raw_body: bytes) -> WebhookEvent:
    event: WebhookEvent | None = None
    snapshot: dict[str, Any] | None = None
    try:
        payload = json.loads(
            raw_body.decode("utf-8"),
            parse_float=Decimal,
            parse_constant=_invalid_json_constant,
            object_pairs_hook=_json_object,
        )
        if not isinstance(payload, dict):
            raise ValueError("Webhook envelope must be an object")
        snapshot = deepcopy(payload)
        webhook_type = payload.get("type")
        if webhook_type == "invoice":
            data = payload.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("event"), str):
                raise ValueError("Invoice webhook requires a string event")
            if data["event"] in ("invoice_status_changed", "payment_status_changed"):
                event = InvoiceWebhook.model_validate(payload)
            else:
                event = UnknownWebhook.model_validate(payload)
        elif webhook_type == "cheque":
            event = ChequeWebhook.model_validate(payload)
        elif webhook_type == "payout":
            event = PayoutWebhook.model_validate(payload)
        elif webhook_type == "withdrawal":
            event = WithdrawalWebhook.model_validate(payload)
        else:
            event = UnknownWebhook.model_validate(payload)
    except (ValueError, TypeError, ArithmeticError, RecursionError):
        # JSON/Unicode/Pydantic exceptions can retain full sensitive input. Do not
        # retain or chain them, even through __context__ with `from None`.
        pass
    if event is None or snapshot is None:
        raise WebhookPayloadError("Authenticated webhook payload did not match the expected schema")
    event._raw_body = raw_body
    event._raw_payload = snapshot
    return event


def verify_and_decode_webhook(
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
    webhook_secret: str | bytes,
    tolerance_ms: int = 300_000,
    clock: Callable[[], int] | None = None,
) -> WebhookEvent:
    """Verify original bytes through P016, then decode a Current Pay event.

    Authentication and time-window failures keep their WebhookError subclasses.
    Invalid authenticated JSON/envelopes/known payloads raise WebhookPayloadError.
    Future type strings or invoice event strings return UnknownWebhook, preserving
    the payload without inferring a payment outcome. Missing/nonstring invoice
    event is malformed, not a future event.

    JSON uses UTF-8 and exact Decimal fractional numbers. Duplicate object keys and
    nonfinite JSON constants are rejected as SDK decoding policy. Envelope dates
    are aware date-time strings, separate from the signing header timestamp.

    Normal event repr/str are redacted. Explicit raw_body/raw_payload properties
    expose authenticated snapshots; dumps and nested DTO access can be sensitive.
    Constructing the public DTOs directly does not authenticate them and does not
    populate these snapshots. No dedupe, ordering, business processing or I/O is
    performed: applications dedupe with the top-level delivery id. Payment finality
    is payment.finalized_at is not None, never a status/event-name inference.
    """
    try:
        verify_webhook_signature(
            raw_body=raw_body,
            headers=headers,
            webhook_secret=webhook_secret,
            tolerance_ms=tolerance_ms,
            clock=clock,
        )
        # HMAC consumes the bytes buffer. Do not let a bytes subclass override
        # decode()/__bytes__ and substitute different JSON after authentication.
        body = raw_body if type(raw_body) is bytes else memoryview(raw_body).tobytes()
        return _decode_verified_body(body)
    except WebhookError as error:
        # Preserve P016's boundary even when called in a sensitive caller handler.
        error.__context__ = None
        error.__cause__ = None
        raise
