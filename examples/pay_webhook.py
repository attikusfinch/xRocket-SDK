"""Framework-neutral authentication of original Current testnet webhook bytes."""

import os
from collections.abc import Mapping

from xrocket.pay import (
    InvoiceWebhook,
    PaymentStatusChangedWebhookData,
    WebhookEvent,
    verify_and_decode_webhook,
)


def decode_delivery(raw_body: bytes, headers: Mapping[str, str]) -> WebhookEvent:
    """Verify raw bytes before JSON using the separate webhook secret, never the JWT.

    The application must deduplicate only the upper delivery ``event.id`` in its
    durable business transaction. Invoice/payment IDs are not delivery IDs. This
    example implements no storage, replay prevention, ordering, or processing.
    Keep raw bytes from the HTTP framework; do not parse or reserialize them first.
    """
    return verify_and_decode_webhook(
        raw_body=raw_body,
        headers=headers,
        webhook_secret=os.environ["XROCKET_PAY_TESTNET_WEBHOOK_SECRET"],
    )


def payment_finality(delivery: WebhookEvent) -> bool | None:
    """Read finalizedAt only for a known payment event; other deliveries return None.

    Finality is not a success classification. Applications must explicitly handle
    supported statuses; unknown status strings must never mean success by default.
    UnknownWebhook payloads require a separate review and have no inferred finality.
    """
    if isinstance(delivery, InvoiceWebhook) and isinstance(
        delivery.data, PaymentStatusChangedWebhookData
    ):
        return delivery.data.payment.finalized_at is not None
    return None
