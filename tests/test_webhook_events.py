"""Authenticated synthetic Current events, future payloads, and safe diagnostics."""

import hashlib
import hmac
import json
import traceback
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

import xrocket
import xrocket.pay as pay
from xrocket.pay import (
    Cheque,
    ChequeWebhook,
    Invoice,
    InvoiceBlockchainTransaction,
    InvoiceInternalTransaction,
    InvoicePayment,
    InvoiceStatusChangedWebhookData,
    InvoiceWebhook,
    PaymentStatusChangedWebhookData,
    Payout,
    PayoutWebhook,
    UnknownInvoiceTransaction,
    UnknownWebhook,
    WebhookError,
    WebhookPayloadError,
    WebhookSignatureError,
    WebhookTimestampError,
    Withdrawal,
    WithdrawalWebhook,
    models,
    verify_and_decode_webhook,
)

NOW_MS = 1_800_000_000_123
SECRET = b"synthetic-event-signing-secret"
SENT_AT = "2026-10-18T10:11:12.123456+05:00"
CREATED_AT = "2026-10-17T02:03:04.654321-03:30"
FINALIZED_AT = "2026-10-18T10:10:11.123456+05:00"
EXACT_AMOUNT = "12345678901234567890.000000000100"
PRIVATE_MARKER = "synthetic-private-callback-marker"


def _invoice(**changes: Any) -> dict[str, Any]:
    return {
        "id": "synthetic-invoice",
        "priceCurrency": "USDT",
        "createdAt": CREATED_AT,
        "status": "active",
        "links": {"telegramBotLink": "https://example.invalid/invoice"},
        **changes,
    }


def _transaction(kind: str = "internal", **changes: Any) -> dict[str, Any]:
    return {
        "id": f"synthetic-{kind}",
        "type": kind,
        "status": "pending",
        "createdAt": CREATED_AT,
        **changes,
    }


def _payment(**changes: Any) -> dict[str, Any]:
    return {
        "status": "pending",
        "payAmount": EXACT_AMOUNT,
        "payCurrency": "USDT",
        "receiveAmount": "0.000000000100",
        "receiveCurrency": "USDT",
        "transactions": [],
        **changes,
    }


def _envelope(kind: str = "invoice", data: Any = None, **changes: Any) -> dict[str, Any]:
    if data is None and kind == "invoice":
        data = {"event": "invoice_status_changed", "invoice": _invoice()}
    return {
        "id": "synthetic-delivery",
        "timestamp": SENT_AT,
        "type": kind,
        "data": data,
        **changes,
    }


def _payment_envelope(**payment_changes: Any) -> dict[str, Any]:
    return _envelope(
        data={
            "event": "payment_status_changed",
            "invoice": _invoice(),
            "payment": _payment(**payment_changes),
        }
    )


def _body(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _headers(body: bytes, timestamp: str = str(NOW_MS)) -> dict[str, str]:
    return {
        "Signature-Timestamp": timestamp,
        "Signature-Version": "v1",
        "Signature": hmac.new(
            SECRET, timestamp.encode("ascii") + b"." + body, hashlib.sha256
        ).hexdigest(),
    }


def _decode(payload: Any, **changes: Any) -> Any:
    body = payload if isinstance(payload, bytes) else _body(payload)
    options: dict[str, Any] = {
        "raw_body": body,
        "headers": _headers(body),
        "webhook_secret": SECRET,
        "clock": lambda: NOW_MS,
    }
    return verify_and_decode_webhook(**(options | changes))


@pytest.mark.parametrize(
    "name",
    [
        "InvoiceWebhook",
        "InvoiceStatusChangedWebhookData",
        "PaymentStatusChangedWebhookData",
        "ChequeWebhook",
        "PayoutWebhook",
        "WithdrawalWebhook",
        "UnknownWebhook",
        "WebhookEvent",
    ],
)
def test_event_models_share_public_imports(name: str) -> None:
    assert name in pay.__all__
    assert name in models.__all__
    assert getattr(pay, name) is getattr(models, name)
    assert not hasattr(xrocket, name)


def test_safe_function_and_payload_error_are_pay_only_exports() -> None:
    assert pay.verify_and_decode_webhook is verify_and_decode_webhook
    assert "verify_and_decode_webhook" in pay.__all__
    assert "WebhookPayloadError" in pay.__all__
    assert issubclass(WebhookPayloadError, WebhookError)
    assert not issubclass(WebhookPayloadError, xrocket.AuthenticationError)
    assert not hasattr(xrocket, "verify_and_decode_webhook")
    assert not hasattr(xrocket, "WebhookPayloadError")


def test_invoice_only_event_decodes_without_payment_and_preserves_aliases() -> None:
    payload = _envelope(
        data={
            "event": "invoice_status_changed",
            "invoice": _invoice(priceAmount=EXACT_AMOUNT, futureInvoice={"flag": True}),
            "futureData": ["kept"],
        },
        futureEnvelope={"revision": 3},
    )
    event = _decode(payload)
    assert isinstance(event, InvoiceWebhook)
    assert isinstance(event.data, InvoiceStatusChangedWebhookData)
    assert isinstance(event.data.invoice, Invoice)
    assert event.id == "synthetic-delivery"
    assert event.type == "invoice"
    assert event.timestamp.isoformat() == SENT_AT
    assert event.timestamp.utcoffset() == timedelta(hours=5)
    assert event.data.invoice.created_at.isoformat() == CREATED_AT
    assert event.data.invoice.price_amount == Decimal(EXACT_AMOUNT)
    assert "payment" not in event.data.model_fields_set
    dumped = event.model_dump(by_alias=True, exclude_unset=True)
    assert dumped["futureEnvelope"] == {"revision": 3}
    assert dumped["data"]["futureData"] == ["kept"]
    assert dumped["data"]["invoice"]["futureInvoice"] == {"flag": True}
    assert dumped["data"]["invoice"]["createdAt"] == event.data.invoice.created_at
    assert "created_at" not in dumped["data"]["invoice"]


def test_payment_event_keeps_typed_payment_and_each_transaction_variant() -> None:
    payload = _payment_envelope(
        transactions=[
            _transaction(payAmount=None, payCurrency=None, finalizedAt=None),
            _transaction(
                "blockchain",
                receiveAmount=None,
                receiveCurrency=None,
                tx={
                    "network": "FUTURE",
                    "txHash": "synthetic-hash",
                    "amount": EXACT_AMOUNT,
                    "currency": "USDT",
                    "status": "future_tx_status",
                },
            ),
            {"type": "future_rail", "futureTransaction": {"amount": EXACT_AMOUNT}},
        ],
        futurePayment={"flag": True},
    )
    event = _decode(payload)
    assert isinstance(event, InvoiceWebhook)
    assert isinstance(event.data, PaymentStatusChangedWebhookData)
    payment = event.data.payment
    assert isinstance(payment, InvoicePayment)
    assert payment.id is None  # PAY-007: the OAS does not require payment id.
    assert payment.pay_amount == Decimal(EXACT_AMOUNT)
    assert payment.receive_amount == Decimal("0.000000000100")
    assert isinstance(payment.transactions[0], InvoiceInternalTransaction)
    assert payment.transactions[0].pay_amount is None
    assert isinstance(payment.transactions[1], InvoiceBlockchainTransaction)
    assert payment.transactions[1].receive_currency is None
    assert payment.transactions[1].tx.amount == Decimal(EXACT_AMOUNT)
    assert payment.transactions[1].tx.status == "future_tx_status"
    assert isinstance(payment.transactions[2], UnknownInvoiceTransaction)
    assert payment.transactions[2].model_dump()["futureTransaction"] == {
        "amount": EXACT_AMOUNT
    }
    assert payment.model_dump()["futurePayment"] == {"flag": True}


@pytest.mark.parametrize("status", ["pending", "paid", "failed", "future_review_status"])
@pytest.mark.parametrize("finalized_at", [None, FINALIZED_AT])
def test_payment_finality_is_independent_of_status(status: str, finalized_at: str | None) -> None:
    event = _decode(_payment_envelope(status=status, finalizedAt=finalized_at))
    payment = event.data.payment
    assert payment.status == status
    assert (payment.finalized_at is not None) is (finalized_at is not None)
    if finalized_at is not None:
        assert payment.finalized_at.isoformat() == finalized_at


@pytest.mark.parametrize(
    "kind,data,envelope_model,data_model",
    [
        (
            "cheque",
            {
                "chequeId": "synthetic-cheque",
                "asset": "USDT",
                "links": {},
                "deleted": False,
                "state": "future_cheque_state",
            },
            ChequeWebhook,
            Cheque,
        ),
        (
            "payout",
            {
                "payoutId": "synthetic-payout",
                "target": "synthetic-target",
                "targetType": "future_target_type",
                "asset": "USDT",
                "amount": EXACT_AMOUNT,
                "status": "future_payout_status",
            },
            PayoutWebhook,
            Payout,
        ),
        (
            "withdrawal",
            {
                "withdrawalId": "synthetic-withdrawal",
                "network": "FUTURE",
                "address": "synthetic-address",
                "asset": "USDT",
                "amount": EXACT_AMOUNT,
                "status": "FUTURE_WITHDRAWAL_STATUS",
            },
            WithdrawalWebhook,
            Withdrawal,
        ),
    ],
)
def test_other_pay_envelopes_use_direct_typed_dto(
    kind: str, data: dict[str, Any], envelope_model: type[Any], data_model: type[Any]
) -> None:
    data = data | {"futureField": {"flag": True}}
    event = _decode(_envelope(kind, data))
    assert isinstance(event, envelope_model)
    assert isinstance(event.data, data_model)
    assert event.type == kind
    assert event.data.model_dump(by_alias=True)["futureField"] == {"flag": True}
    if kind in ("payout", "withdrawal"):
        assert event.data.amount == Decimal(EXACT_AMOUNT)
    assert event.raw_payload["data"] == data


@pytest.mark.parametrize("kind", ["future_type", "Invoice", "INVOICE", "", "invoice.v2"])
@pytest.mark.parametrize("data", [None, True, 7, "future", [1, {"flag": True}], {"new": []}])
def test_unknown_type_keeps_arbitrary_json_data_without_financial_interpretation(
    kind: str, data: Any
) -> None:
    payload = _envelope(kind, data, futureEnvelope={"kept": True})
    event = _decode(payload)
    assert isinstance(event, UnknownWebhook)
    assert event.type == kind
    assert event.data == data
    assert event.raw_payload == payload
    assert event.model_dump(by_alias=True)["futureEnvelope"] == {"kept": True}


@pytest.mark.parametrize("name", ["invoice_future_changed", "PAYMENT_STATUS_CHANGED", ""])
def test_unknown_invoice_event_keeps_whole_payload_without_requiring_known_dto(name: str) -> None:
    payload = _envelope(
        data={
            "event": name,
            "invoice": {"status": "paid"},
            "payment": {"status": "failed"},
            "future": {"nested": [1, 2]},
        }
    )
    event = _decode(payload)
    assert isinstance(event, UnknownWebhook)
    assert event.type == "invoice"
    assert event.data == payload["data"]
    assert isinstance(event.data["payment"], dict)
    assert event.raw_payload == payload


def test_exact_json_decimal_numbers_and_original_bytes_are_preserved() -> None:
    payload = _payment_envelope()
    payload["data"]["invoice"]["status"] = "future_invoice_status"
    payload["futureNumber"] = "RAW_NUMBER"
    body = (
        b" \r\n"
        + _body(payload).replace(
            f'"{EXACT_AMOUNT}"'.encode(), EXACT_AMOUNT.encode()
        ).replace(b'"RAW_NUMBER"', b"0.123456789012345678901234567890123456789")
        + b"\r\n"
    )
    event = _decode(body)
    assert event.raw_body == body
    assert event.data.invoice.status == "future_invoice_status"
    assert event.data.payment.pay_amount == Decimal(EXACT_AMOUNT)
    assert event.raw_payload["data"]["payment"]["payAmount"] == Decimal(EXACT_AMOUNT)
    assert event.raw_payload["futureNumber"] == Decimal(
        "0.123456789012345678901234567890123456789"
    )
    assert event.model_dump()["futureNumber"] == event.raw_payload["futureNumber"]


def test_raw_payload_is_an_independent_snapshot_for_each_access() -> None:
    payload = _envelope(data={"event": "future", "nested": {"list": [1, 2]}})
    body = _body(payload)
    event = _decode(body)
    first = event.raw_payload
    first["id"] = "changed"
    first["data"]["nested"]["list"].append(3)
    event.data["nested"]["list"].append(4)
    assert event.raw_payload == payload
    assert event.raw_body == body


@pytest.mark.parametrize(
    "model,payload",
    [
        (InvoiceWebhook, _envelope()),
        (InvoiceWebhook, _payment_envelope()),
        (UnknownWebhook, _envelope("future", {"flag": True})),
    ],
)
@pytest.mark.parametrize("attribute", ["raw_body", "raw_payload"])
def test_manually_validated_dto_does_not_claim_authenticated_raw(
    model: type[Any], payload: dict[str, Any], attribute: str
) -> None:
    event = model.model_validate(deepcopy(payload))
    with pytest.raises(RuntimeError):
        getattr(event, attribute)


@pytest.mark.parametrize("attribute", ["raw_body", "raw_payload"])
def test_wire_extras_cannot_spoof_authenticated_snapshots(attribute: str) -> None:
    payload = _envelope(
        "future",
        {"flag": True},
        _raw_body="synthetic-spoofed-body",
        _raw_payload={"spoofed": True},
        raw_body="synthetic-spoofed-body",
        raw_payload={"spoofed": True},
    )
    manual = UnknownWebhook.model_validate(deepcopy(payload))
    with pytest.raises(RuntimeError):
        getattr(manual, attribute)
    authenticated = _decode(payload)
    assert authenticated.raw_body == _body(payload)
    assert authenticated.raw_payload == payload


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not JSON",
        b"\xff\xfe",
        b'{"data":',
        b"null",
        b"[]",
        b"123",
        b'"text"',
        b"true",
    ],
)
def test_authenticated_bad_json_utf8_or_top_level_shape_is_payload_error(body: bytes) -> None:
    with pytest.raises(WebhookPayloadError):
        _decode(body)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_constants_are_rejected_even_for_unknown_type(value: str) -> None:
    body = _body(_envelope("future", {})).replace(b'"data":{}', f'"data":{value}'.encode())
    with pytest.raises(WebhookPayloadError):
        _decode(body)


@pytest.mark.parametrize(
    "body",
    [
        _body(_envelope()).replace(b'"id":"synthetic-delivery"', b'"id":"a","id":"b"'),
        _body(_envelope("future", {})).replace(b'"data":{}', b'"data":{"a":1,"a":2}'),
        _body(_envelope("future", {})).replace(
            b'"data":{}', b'"data":{"a":1,"\\u0061":2}'
        ),
    ],
)
def test_duplicate_json_keys_are_rejected_at_every_level(body: bytes) -> None:
    with pytest.raises(WebhookPayloadError):
        _decode(body)


@pytest.mark.parametrize("field", ["id", "timestamp", "type", "data"])
@pytest.mark.parametrize("kind", ["invoice", "future"])
def test_missing_envelope_fields_never_become_fallback(field: str, kind: str) -> None:
    payload = _envelope(kind, {})
    del payload[field]
    with pytest.raises(WebhookPayloadError):
        _decode(payload)


@pytest.mark.parametrize(
    "timestamp",
    [
        None,
        True,
        1_800_000_000,
        "1800000000",
        "1800000000.123",
        "2026-10-18T10:11:12",
        "bad",
    ],
)
@pytest.mark.parametrize("kind", ["invoice", "future"])
def test_envelope_timestamp_requires_aware_wire_datetime_string(timestamp: Any, kind: str) -> None:
    with pytest.raises(WebhookPayloadError):
        _decode(_envelope(kind, {}, timestamp=timestamp))


@pytest.mark.parametrize("field", ["id", "type"])
@pytest.mark.parametrize("value", [None, 1, True, [], {}])
def test_envelope_identifiers_are_strings(field: str, value: Any) -> None:
    with pytest.raises(WebhookPayloadError):
        _decode(_envelope("future", {}, **{field: value}))


@pytest.mark.parametrize("data", [None, [], "event", 1, True, {}, {"event": None}, {"event": 1}])
def test_missing_or_nonstring_invoice_event_is_malformed(data: Any) -> None:
    payload = _envelope()
    payload["data"] = data
    with pytest.raises(WebhookPayloadError):
        _decode(payload)


@pytest.mark.parametrize(
    "data",
    [
        {"event": "invoice_status_changed"},
        {"event": "invoice_status_changed", "invoice": None},
        {"event": "invoice_status_changed", "invoice": {"status": "paid"}},
        {"event": "payment_status_changed", "invoice": _invoice()},
        {"event": "payment_status_changed", "invoice": _invoice(), "payment": None},
        {"event": "payment_status_changed", "invoice": _invoice(), "payment": {"status": "paid"}},
    ],
)
def test_malformed_known_invoice_variants_never_fall_back(data: dict[str, Any]) -> None:
    with pytest.raises(WebhookPayloadError):
        _decode(_envelope(data=data))


@pytest.mark.parametrize("kind", ["cheque", "payout", "withdrawal"])
@pytest.mark.parametrize("data", [{}, None, [], "payload"])
def test_malformed_other_known_types_never_fall_back(kind: str, data: Any) -> None:
    with pytest.raises(WebhookPayloadError):
        _decode(_envelope(kind, data))


@pytest.mark.parametrize(
    "transaction",
    [
        {"type": "internal"},
        {"type": "blockchain"},
        {"id": "synthetic-transaction", "status": "paid", "createdAt": CREATED_AT},
        {"type": None},
        {"type": 1},
    ],
)
def test_malformed_known_or_undiscriminated_transactions_are_payload_errors(
    transaction: dict[str, Any],
) -> None:
    with pytest.raises(WebhookPayloadError):
        _decode(_payment_envelope(transactions=[transaction]))


@pytest.mark.parametrize(
    "body", [b"not JSON", b"\xff", _body(_payment_envelope(transactions=[{}]))]
)
def test_invalid_signature_wins_before_json_or_dto_validation(
    body: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = _headers(body)
    headers["Signature"] = "0" * 64

    def no_json(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Unauthenticated bytes reached JSON parsing")

    monkeypatch.setattr(json, "loads", no_json)
    with pytest.raises(WebhookSignatureError):
        _decode(body, headers=headers)


def test_authenticated_timestamp_failure_precedes_json_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b"not JSON"

    def no_json(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("An out-of-window delivery reached JSON parsing")

    monkeypatch.setattr(json, "loads", no_json)
    with pytest.raises(WebhookTimestampError):
        _decode(body, clock=lambda: NOW_MS + 300_001)


def test_modified_body_is_not_authenticated_by_reserialization() -> None:
    original = _body(_envelope())
    modified = original + b"\n"
    with pytest.raises(WebhookSignatureError):
        _decode(modified, headers=_headers(original))
    assert _decode(modified).raw_body == modified


def test_bytes_subclass_cannot_substitute_unsigned_json_after_verification() -> None:
    signed = _body(_envelope("future", {"signed": True}, id="signed-delivery"))
    unsigned = _body(_envelope("future", {"signed": False}, id="unsigned-delivery"))

    class Body(bytes):
        def decode(self, *args: Any, **kwargs: Any) -> str:
            return unsigned.decode()

        def __bytes__(self) -> bytes:
            return unsigned

    body = Body(signed)
    event = _decode(body)
    assert event.id == "signed-delivery"
    assert event.raw_payload == json.loads(signed)
    assert type(event.raw_body) is bytes
    assert event.raw_body == signed
    assert event.raw_body.decode() == signed.decode()


def test_repeat_and_out_of_order_delivery_remain_independent_by_envelope_id() -> None:
    payment = _payment_envelope(id="same-business-payment", status="paid", finalizedAt=FINALIZED_AT)
    payment["id"] = "delivery-payment"
    invoice = _envelope(
        data={"event": "invoice_status_changed", "invoice": _invoice(status="paid")},
        id="delivery-invoice",
        timestamp="2026-10-18T10:11:10+05:00",
    )
    # Invoice completion can arrive first; signing-window checks are stateless.
    delivered = [_decode(invoice), _decode(payment), _decode(payment)]
    assert [event.id for event in delivered] == [
        "delivery-invoice",
        "delivery-payment",
        "delivery-payment",
    ]
    assert isinstance(delivered[0].data, InvoiceStatusChangedWebhookData)
    assert isinstance(delivered[1].data, PaymentStatusChangedWebhookData)
    assert delivered[1].data.payment.id == "same-business-payment"
    assert delivered[1].data.invoice.id == delivered[0].data.invoice.id
    # This example deliberately uses delivery ids, rather than either business id.
    seen: set[str] = set()
    accepted = []
    for event in delivered:
        if event.id not in seen:
            seen.add(event.id)
            accepted.append(event)
    assert len(accepted) == 2
    assert seen == {"delivery-invoice", "delivery-payment"}


@pytest.mark.parametrize("payment_variant", [False, True])
def test_known_envelope_and_invoice_variant_repr_hide_data_and_extras(
    payment_variant: bool,
) -> None:
    payload = _payment_envelope() if payment_variant else _envelope()
    payload["id"] = PRIVATE_MARKER
    payload["futureEnvelope"] = PRIVATE_MARKER
    payload["data"]["futureData"] = PRIVATE_MARKER
    payload["data"]["invoice"]["callback"] = {"payload": {"private": PRIVATE_MARKER}}
    event = _decode(payload)
    for value in (event, event.data):
        assert PRIVATE_MARKER not in repr(value)
        assert PRIVATE_MARKER not in str(value)
        assert EXACT_AMOUNT not in repr(value)
    other = _decode(_payment_envelope() if payment_variant else _envelope())
    assert repr(event) == repr(other)
    assert str(event) == str(other)
    assert repr(event.data) == repr(other.data)
    assert str(event.data) == str(other.data)
    assert PRIVATE_MARKER in event.raw_body.decode()


def test_unknown_repr_hides_arbitrary_raw_payload_and_envelope_extras() -> None:
    event = _decode(_envelope("future", {"private": PRIVATE_MARKER}, extra=PRIVATE_MARKER))
    other = _decode(_envelope("other_future", ["different"]))
    assert PRIVATE_MARKER not in repr(event)
    assert PRIVATE_MARKER not in str(event)
    assert repr(event) == repr(other)
    assert str(event) == str(other)
    assert event.raw_payload["data"]["private"] == PRIVATE_MARKER


@pytest.mark.parametrize(
    "kind,data",
    [
        (
            "cheque",
            {"chequeId": "synthetic", "asset": "USDT", "links": {}, "deleted": True},
        ),
        (
            "payout",
            {
                "payoutId": "synthetic",
                "target": "synthetic",
                "targetType": "future",
                "asset": "USDT",
                "amount": EXACT_AMOUNT,
                "status": "future",
            },
        ),
        (
            "withdrawal",
            {
                "withdrawalId": "synthetic",
                "network": "future",
                "address": "synthetic",
                "asset": "USDT",
                "amount": EXACT_AMOUNT,
            },
        ),
    ],
)
def test_other_known_envelope_repr_hides_sensitive_direct_dto(
    kind: str, data: dict[str, Any]
) -> None:
    payload = _envelope(
        kind, data | {"callback": {"payload": {"private": PRIVATE_MARKER}}}, id=PRIVATE_MARKER
    )
    event = _decode(payload)
    assert PRIVATE_MARKER not in repr(event)
    assert PRIVATE_MARKER not in str(event)
    assert EXACT_AMOUNT not in repr(event)
    assert EXACT_AMOUNT not in str(event)
    assert event.raw_payload == payload


@pytest.mark.parametrize(
    "body",
    [
        (f'{{"private":"{PRIVATE_MARKER}",').encode(),
        _body(_envelope(data={"event": "payment_status_changed", "invoice": PRIVATE_MARKER})),
        _body(_envelope("payout", {"amount": PRIVATE_MARKER})),
        _body(_payment_envelope(payAmount=PRIVATE_MARKER)),
        b"\xff" + PRIVATE_MARKER.encode(),
    ],
)
def test_payload_error_diagnostics_do_not_retain_sensitive_inputs(body: bytes) -> None:
    with pytest.raises(WebhookPayloadError) as caught:
        _decode(body)
    error = caught.value
    diagnostic = " ".join(
        [
            str(error),
            repr(error),
            repr(error.args),
            repr(vars(error)),
            *traceback.format_exception(error),
        ]
    )
    assert PRIVATE_MARKER not in diagnostic
    assert SECRET.decode() not in diagnostic
    assert body.decode("utf-8", errors="replace") not in diagnostic
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.mark.parametrize("invalid_signature", [False, True])
def test_safe_boundary_clears_sensitive_ambient_caller_exception(invalid_signature: bool) -> None:
    body = _body(_payment_envelope(payAmount=PRIVATE_MARKER))
    headers = _headers(body)
    if invalid_signature:
        headers["Signature"] = "0" * 64
    expected = WebhookSignatureError if invalid_signature else WebhookPayloadError
    try:
        raise ValueError(PRIVATE_MARKER, SECRET)
    except ValueError:
        with pytest.raises(expected) as caught:
            _decode(body, headers=headers)
    error = caught.value
    assert error.__cause__ is None
    assert error.__context__ is None
    diagnostic = "".join(traceback.format_exception(error)) + repr(error.args)
    assert PRIVATE_MARKER not in diagnostic
    assert SECRET.decode() not in diagnostic
