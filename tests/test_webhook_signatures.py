"""Synthetic Current signing vectors, exact wire bytes, local replay policy and redaction."""

import hashlib
import hmac
import json
import traceback
from decimal import Inexact, localcontext
from typing import Any

import httpx
import pytest

import xrocket
import xrocket.pay as pay
import xrocket.pay.webhooks as webhooks
from xrocket import XRocketError
from xrocket.pay import (
    WebhookConfigurationError,
    WebhookError,
    WebhookHeaderError,
    WebhookSignatureError,
    WebhookTimestampError,
    verify_webhook_signature,
)

NOW_MS = 1_800_000_000_123
SECRET = b"synthetic-current-webhook-secret"
BODY = '{ "label": "синтетика 🚀", "timestamp": 1, "data": {} }\n'.encode()


def _headers(
    body: bytes = BODY,
    *,
    timestamp: str = str(NOW_MS),
    secret: bytes = SECRET,
) -> dict[str, str]:
    return {
        "Signature-Timestamp": timestamp,
        "Signature-Version": "v1",
        "Signature": hmac.new(secret, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest(),
    }


def _verify(**changes: Any) -> None:
    options: dict[str, Any] = {
        "raw_body": BODY,
        "headers": _headers(),
        "webhook_secret": SECRET,
        "clock": lambda: NOW_MS,
    }
    verify_webhook_signature(**(options | changes))


@pytest.mark.parametrize(
    "timestamp,body,signature",
    [
        (
            "1730000000123",
            b'{"amount":"1.00"}',
            "cf04c30b5971bd24e3fdefe59b7f2faf488557793ab6c3938d1c5397638192d8",
        ),
        (
            "01730000000123",
            b'{"amount":"1.00"}',
            "ccd80dd6463e814e8022f28d520c565430db2e085f79e4a3cc7de0449e0d27c5",
        ),
        (
            "1730000000123",
            bytes.fromhex(
                "7b20226d657373616765223a2022d09fd180d0b8d0b2d0b5d18220f09f8c8d22207d0d0a"
            ),
            "7f4d110594b4db1e790d27ea8f5dfa17c5a1e839cbe23f818b4ab7ecf873489b",
        ),
    ],
)
def test_independent_known_answer_vectors(timestamp: str, body: bytes, signature: str) -> None:
    # Literal answers computed separately with the RFC 2104 ipad/opad construction
    # over hashlib, cross-checked against RFC 4231 case 1 and stdlib hmac.digest.
    # This test deliberately does not call the generated-signature fixture helper.
    verify_webhook_signature(
        raw_body=body,
        headers={
            "Signature-Timestamp": timestamp,
            "Signature-Version": "v1",
            "Signature": signature,
        },
        webhook_secret="synthetic-webhook-secret",
        tolerance_ms=0,
        clock=lambda: 1_730_000_000_123,
    )


def test_public_exports_and_product_isolation() -> None:
    for name in (
        "verify_webhook_signature",
        "WebhookError",
        "WebhookConfigurationError",
        "WebhookHeaderError",
        "WebhookSignatureError",
        "WebhookTimestampError",
    ):
        assert name in pay.__all__
        assert getattr(pay, name) is globals()[name]
        assert not hasattr(xrocket, name)
    assert issubclass(WebhookError, XRocketError)
    for error in (
        WebhookConfigurationError,
        WebhookHeaderError,
        WebhookSignatureError,
        WebhookTimestampError,
    ):
        assert issubclass(error, WebhookError)
        assert not issubclass(error, xrocket.AuthenticationError)
    assert pay.PayClient and pay.AsyncPayClient and pay.InvoicePayment


@pytest.mark.parametrize("body", [b"", b"not JSON", b"\x00\xff\xfe", BODY])
def test_exact_arbitrary_bytes_verify_without_json_decoding(
    body: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_json(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("signature verification must not parse JSON")

    monkeypatch.setattr(json, "loads", no_json)
    monkeypatch.setattr(json, "dumps", no_json)
    assert _verify(raw_body=body, headers=_headers(body)) is None
    with pytest.raises(WebhookSignatureError):
        _verify(raw_body=body + b" ", headers=_headers(body))


@pytest.mark.parametrize(
    "changed",
    [
        BODY.rstrip(b"\n"),
        BODY.replace(b" ", b""),
        BODY.replace(b"1", b"2"),
        BODY.replace("🚀".encode(), b"\\ud83d\\ude80"),
        BODY.replace(b"\n", b"\r\n"),
        BODY + b"\x00",
        b"\xef\xbb\xbf" + BODY,
        BODY[:-1],
    ],
)
def test_each_raw_byte_change_rejected(changed: bytes) -> None:
    with pytest.raises(WebhookSignatureError):
        _verify(raw_body=changed)


def test_json_reserialization_changes_signature() -> None:
    reserialized = json.dumps(json.loads(BODY), ensure_ascii=False).encode()
    assert json.loads(reserialized) == json.loads(BODY)
    with pytest.raises(WebhookSignatureError):
        _verify(raw_body=reserialized)


def test_changed_timestamp_and_signature_rejected() -> None:
    headers = _headers()
    headers["Signature-Timestamp"] = str(NOW_MS + 1)
    with pytest.raises(WebhookSignatureError):
        _verify(headers=headers)
    headers = _headers()
    first = "0" if headers["Signature"][0] != "0" else "1"
    headers["Signature"] = first + headers["Signature"][1:]
    with pytest.raises(WebhookSignatureError):
        _verify(headers=headers)


@pytest.mark.parametrize("secret", [b"wrong-secret", hashlib.sha256(SECRET).digest()])
def test_wrong_or_legacy_transformed_secret_rejected(secret: bytes) -> None:
    with pytest.raises(WebhookSignatureError):
        _verify(webhook_secret=secret)


@pytest.mark.parametrize("secret", [b" \x00\xff ", " синтетический 🚀 secret ", SECRET])
def test_secret_is_direct_bytes_or_exact_utf8_without_trimming(secret: str | bytes) -> None:
    key = secret.encode() if isinstance(secret, str) else secret
    _verify(headers=_headers(secret=key), webhook_secret=secret)


def test_timestamp_wire_representation_is_signed_verbatim() -> None:
    timestamp = "000" + str(NOW_MS)
    headers = _headers(timestamp=timestamp)
    _verify(headers=headers)
    headers["Signature-Timestamp"] = str(NOW_MS)
    with pytest.raises(WebhookSignatureError):
        _verify(headers=headers)
    headers = _headers()
    headers["Signature-Timestamp"] = timestamp
    with pytest.raises(WebhookSignatureError):
        _verify(headers=headers)


@pytest.mark.parametrize("name", ["Signature-Timestamp", "Signature-Version", "Signature"])
def test_missing_header_rejected(name: str) -> None:
    headers = _headers()
    del headers[name]
    with pytest.raises(WebhookHeaderError):
        _verify(headers=headers)


@pytest.mark.parametrize("name", ["Signature-Timestamp", "Signature-Version", "Signature"])
@pytest.mark.parametrize("value", [None, 123, b"v1", [], True])
def test_nonstring_signing_header_rejected(name: str, value: Any) -> None:
    headers: dict[str, Any] = _headers()
    headers[name] = value
    with pytest.raises(WebhookHeaderError):
        _verify(headers=headers)


@pytest.mark.parametrize("headers", [None, [], "headers", {1: "value"}])
def test_malformed_header_container_rejected(headers: Any) -> None:
    with pytest.raises(WebhookHeaderError):
        _verify(headers=headers)


@pytest.mark.parametrize("name", ["Signature-Timestamp", "Signature-Version", "Signature"])
def test_duplicate_case_variants_and_coalesced_headers_rejected(name: str) -> None:
    headers = _headers()
    headers[name.lower()] = headers[name]
    with pytest.raises(WebhookHeaderError):
        _verify(headers=headers)
    # HTTP libraries can coalesce same-name duplicates to a comma-separated value.
    raw_headers = list(_headers().items()) + [(name, _headers()[name])]
    with pytest.raises(WebhookHeaderError):
        _verify(headers=httpx.Headers(raw_headers))


def test_case_insensitive_names_uppercase_hex_and_unrelated_headers() -> None:
    headers = {name.swapcase(): value for name, value in _headers().items()}
    headers["sIGNATURE"] = headers["sIGNATURE"].upper()
    headers["Content-Type"] = "application/json"
    _verify(headers=headers)
    _verify(headers=httpx.Headers(_headers()))


@pytest.mark.parametrize(
    "timestamp",
    [
        "",
        " ",
        " 1800000000123",
        "1800000000123 ",
        "1800000000123\n",
        "+1800000000123",
        "-1",
        "1800000000.123",
        "1e12",
        "1_800_000_000_123",
        "١٨٠٠٠٠٠٠٠٠١٢٣",
        "１８００００００００１２３",
        "0x123",
        "\x00123",
        "\ud800",
    ],
)
def test_malformed_timestamp_rejected(timestamp: str) -> None:
    headers = _headers()
    headers["Signature-Timestamp"] = timestamp
    with pytest.raises(WebhookHeaderError):
        _verify(headers=headers)


@pytest.mark.parametrize("version", ["", "V1", "v2", "v0", " v1", "v1 ", "v1\n", "v1,v1"])
def test_malformed_or_unsupported_version_rejected(version: str) -> None:
    headers = _headers()
    headers["Signature-Version"] = version
    with pytest.raises(WebhookHeaderError):
        _verify(headers=headers)


@pytest.mark.parametrize(
    "signature",
    [
        "",
        "a" * 63,
        "a" * 65,
        "g" * 64,
        "０" * 64,
        "é" * 64,
        "a" * 64 + "\n",
        " " + "a" * 64,
        "a " * 32,
        "sha256=" + "a" * 64,
        "\ud800",
    ],
)
def test_malformed_signature_rejected(signature: str) -> None:
    headers = _headers()
    headers["Signature"] = signature
    with pytest.raises(WebhookHeaderError):
        _verify(headers=headers)


@pytest.mark.parametrize("offset", [-300_000, -299_999, 0, 299_999, 300_000])
def test_default_inclusive_time_boundaries(offset: int) -> None:
    _verify(headers=_headers(timestamp=str(NOW_MS + offset)))


@pytest.mark.parametrize("offset", [-300_001, 300_001, -NOW_MS, NOW_MS * 100])
def test_stale_or_future_delivery_rejected(offset: int) -> None:
    with pytest.raises(WebhookTimestampError):
        _verify(headers=_headers(timestamp=str(NOW_MS + offset)))


@pytest.mark.parametrize("timestamp", ["9" * 5000, "0" * 5000])
def test_large_decimal_timestamp_is_sanitized_without_int_conversion(timestamp: str) -> None:
    with pytest.raises(WebhookTimestampError) as caught:
        _verify(headers=_headers(timestamp=timestamp))
    assert caught.value.__context__ is None


def test_many_leading_zeros_do_not_change_freshness_or_wire_bytes() -> None:
    _verify(headers=_headers(timestamp="0" * 5000 + str(NOW_MS)))


def test_large_integer_clock_and_tolerance_do_not_expose_conversion_errors() -> None:
    with localcontext() as context:
        context.prec = 1
        context.traps[Inexact] = True
        _verify(tolerance_ms=10**5000)
        with pytest.raises(WebhookTimestampError):
            _verify(clock=lambda: 10**5000)
        _verify(
            clock=lambda: 10**5000,
            headers=_headers(timestamp="1" + "0" * 5000),
            tolerance_ms=0,
        )


@pytest.mark.parametrize("tolerance", [0, 1, 123, 999_999])
def test_custom_tolerance_and_exact_zero(tolerance: int) -> None:
    for offset in {-tolerance, 0, tolerance}:
        _verify(tolerance_ms=tolerance, headers=_headers(timestamp=str(NOW_MS + offset)))
    for offset in {-tolerance - 1, tolerance + 1}:
        with pytest.raises(WebhookTimestampError):
            _verify(tolerance_ms=tolerance, headers=_headers(timestamp=str(NOW_MS + offset)))


def test_unix_epoch_boundary() -> None:
    _verify(clock=lambda: 0, headers=_headers(timestamp="0"), tolerance_ms=0)
    _verify(clock=lambda: 0, headers=_headers(timestamp="10"), tolerance_ms=10)
    with pytest.raises(WebhookTimestampError):
        _verify(clock=lambda: 0, headers=_headers(timestamp="11"), tolerance_ms=10)


def test_milliseconds_are_not_seconds() -> None:
    with pytest.raises(WebhookTimestampError):
        _verify(headers=_headers(timestamp=str(NOW_MS // 1000)))


def test_default_clock_uses_unix_milliseconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(webhooks.time, "time_ns", lambda: NOW_MS * 1_000_000 + 999_999)
    _verify(clock=None, tolerance_ms=0)


def test_time_window_is_not_delivery_deduplication() -> None:
    for _ in range(2):
        _verify()


def test_constant_time_digest_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    original = hmac.compare_digest
    calls: list[tuple[bytes, bytes]] = []

    def compare(left: bytes, right: bytes) -> bool:
        calls.append((left, right))
        return original(left, right)

    monkeypatch.setattr(hmac, "compare_digest", compare)
    _verify()
    with pytest.raises(WebhookSignatureError):
        _verify(webhook_secret=b"wrong")
    assert len(calls) == 2
    assert all(len(left) == len(right) == 32 for left, right in calls)


def test_authentication_precedes_clock_and_freshness() -> None:
    def no_clock() -> int:
        pytest.fail("unauthenticated data must not reach freshness policy")

    with pytest.raises(WebhookSignatureError):
        _verify(headers=_headers(timestamp="0"), webhook_secret=b"wrong", clock=no_clock)


@pytest.mark.parametrize("value", [-1, True, 0.5, "300000", None])
def test_invalid_tolerance_rejected(value: Any) -> None:
    with pytest.raises(WebhookConfigurationError):
        _verify(tolerance_ms=value)


@pytest.mark.parametrize("value", [-1, True, 1.5, "1800000000123", None])
def test_invalid_clock_result_rejected(value: Any) -> None:
    with pytest.raises(WebhookConfigurationError):
        _verify(clock=lambda: value)


@pytest.mark.parametrize("value", [b"", "", None, 123, bytearray(SECRET), "secret\ud800"])
def test_invalid_secret_rejected(value: Any) -> None:
    with pytest.raises(WebhookConfigurationError) as caught:
        _verify(webhook_secret=value)
    assert caught.value.__context__ is None


@pytest.mark.parametrize("value", [BODY.decode(), bytearray(BODY), memoryview(BODY), None, {}])
def test_nonbytes_body_rejected(value: Any) -> None:
    with pytest.raises(WebhookConfigurationError):
        _verify(raw_body=value)


def _secret_clock() -> int:
    raise ValueError(SECRET.decode(), BODY.decode())


@pytest.mark.parametrize(
    "changes,error_type",
    [
        ({"webhook_secret": SECRET.decode() + "\ud800"}, WebhookConfigurationError),
        ({"raw_body": BODY.decode()}, WebhookConfigurationError),
        ({"clock": _secret_clock}, WebhookConfigurationError),
        ({"clock": lambda: BODY.decode()}, WebhookConfigurationError),
        ({"tolerance_ms": BODY.decode()}, WebhookConfigurationError),
        ({"headers": {"Signature": BODY.decode()}}, WebhookHeaderError),
        ({"webhook_secret": b"wrong"}, WebhookSignatureError),
        ({"headers": _headers(timestamp="0")}, WebhookTimestampError),
        *[
            ({"headers": _headers() | {name: SECRET.decode() + BODY.decode()}}, WebhookHeaderError)
            for name in ("Signature", "Signature-Timestamp", "Signature-Version")
        ],
    ],
)
def test_failures_do_not_retain_sensitive_diagnostics(
    changes: dict[str, Any], error_type: type[WebhookError]
) -> None:
    with pytest.raises(error_type) as caught:
        _verify(**changes)
    error = caught.value
    diagnostics = "\n".join(
        [
            str(error),
            repr(error),
            repr(error.args),
            repr(vars(error)),
            "".join(traceback.format_exception(error)),
        ]
    )
    assert SECRET.decode() not in diagnostics
    assert BODY.decode() not in diagnostics
    assert vars(error) == {}
    assert error.__cause__ is None
    assert error.__context__ is None


def test_noncallable_clock_is_sanitized() -> None:
    with pytest.raises(WebhookConfigurationError) as caught:
        _verify(clock=SECRET)
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "changes,error_type",
    [
        ({"tolerance_ms": -1}, WebhookConfigurationError),
        ({"headers": {}}, WebhookHeaderError),
        ({"webhook_secret": b"wrong"}, WebhookSignatureError),
        ({"headers": _headers(timestamp="0")}, WebhookTimestampError),
        ({"clock": _secret_clock}, WebhookConfigurationError),
    ],
)
def test_sensitive_caller_exception_context_is_not_attached(
    changes: dict[str, Any], error_type: type[WebhookError]
) -> None:
    try:
        raise ValueError(SECRET.decode(), BODY.decode())
    except ValueError:
        with pytest.raises(error_type) as caught:
            _verify(**changes)
    error = caught.value
    assert error.__context__ is None
    assert error.__cause__ is None
    diagnostics = "".join(traceback.format_exception(error))
    assert SECRET.decode() not in diagnostics
    assert BODY.decode() not in diagnostics


def test_function_has_no_persistent_secret_or_client_dependency() -> None:
    assert vars(verify_webhook_signature) == {}
    _verify()
    assert vars(verify_webhook_signature) == {}
    assert not isinstance(verify_webhook_signature, (pay.PayClient, pay.AsyncPayClient))
