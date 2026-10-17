"""Private read-only testnet smoke; identifiers are explicit env fixtures only."""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

import pytest

from xrocket.pay import AsyncPayClient, PayClient
from xrocket.pay.models import (
    AppBalances,
    AppInfo,
    Cheque,
    CursorPage,
    Invoice,
    InvoicePaymentPage,
    Payout,
    Withdrawal,
    WithdrawalQuotas,
)

pytestmark = pytest.mark.live

Client = PayClient | AsyncPayClient
LiveCall = Callable[..., Awaitable[Any]]
IdentifierKind = Literal["server_id", "client_id"]


async def test_private_testnet_app_info(private_pay: Client, private_live_call: LiveCall) -> None:
    if not isinstance(await private_live_call(private_pay.app.info), AppInfo):
        pytest.fail("Expected a typed testnet application response", pytrace=False)


async def test_private_testnet_balances(private_pay: Client, private_live_call: LiveCall) -> None:
    if not isinstance(await private_live_call(private_pay.app.balances), AppBalances):
        pytest.fail("Expected a typed testnet balances response", pytrace=False)


async def test_private_testnet_invoices_list(
    private_pay: Client, private_live_call: LiveCall
) -> None:
    if not isinstance(await private_live_call(private_pay.invoices.list, limit=1), CursorPage):
        pytest.fail("Expected a typed testnet invoices page", pytrace=False)


async def test_private_testnet_cheques_list(
    private_pay: Client, private_live_call: LiveCall
) -> None:
    if not isinstance(await private_live_call(private_pay.cheques.list, limit=1), CursorPage):
        pytest.fail("Expected a typed testnet cheques page", pytrace=False)


async def test_private_testnet_payouts_list(
    private_pay: Client, private_live_call: LiveCall
) -> None:
    if not isinstance(await private_live_call(private_pay.payouts.list, limit=1), CursorPage):
        pytest.fail("Expected a typed testnet payouts page", pytrace=False)


async def test_private_testnet_withdrawals_list(
    private_pay: Client, private_live_call: LiveCall
) -> None:
    if not isinstance(await private_live_call(private_pay.withdrawals.list, limit=1), CursorPage):
        pytest.fail("Expected a typed testnet withdrawals page", pytrace=False)


async def test_private_testnet_invoice_retrieve(
    private_pay: Client, private_live_call: LiveCall, identifier_kind: IdentifierKind
) -> None:
    if not isinstance(
        await private_live_call(
            private_pay.invoices.retrieve,
            identifier_resource="invoice",
            identifier_kind=identifier_kind,
        ),
        Invoice,
    ):
        pytest.fail("Expected a typed testnet invoice response", pytrace=False)


async def test_private_testnet_invoice_payments(
    private_pay: Client, private_live_call: LiveCall, identifier_kind: IdentifierKind
) -> None:
    if not isinstance(
        await private_live_call(
            private_pay.invoices.payments,
            identifier_resource="invoice",
            identifier_kind=identifier_kind,
            limit=1,
        ),
        InvoicePaymentPage,
    ):
        pytest.fail("Expected a typed testnet invoice payments page", pytrace=False)


async def test_private_testnet_cheque_retrieve(
    private_pay: Client, private_live_call: LiveCall, identifier_kind: IdentifierKind
) -> None:
    if not isinstance(
        await private_live_call(
            private_pay.cheques.retrieve,
            identifier_resource="cheque",
            identifier_kind=identifier_kind,
        ),
        Cheque,
    ):
        pytest.fail("Expected a typed testnet cheque response", pytrace=False)


async def test_private_testnet_payout_retrieve(
    private_pay: Client, private_live_call: LiveCall, identifier_kind: IdentifierKind
) -> None:
    if not isinstance(
        await private_live_call(
            private_pay.payouts.retrieve,
            identifier_resource="payout",
            identifier_kind=identifier_kind,
        ),
        Payout,
    ):
        pytest.fail("Expected a typed testnet payout response", pytrace=False)


async def test_private_testnet_withdrawal_retrieve(
    private_pay: Client, private_live_call: LiveCall, identifier_kind: IdentifierKind
) -> None:
    if not isinstance(
        await private_live_call(
            private_pay.withdrawals.retrieve,
            identifier_resource="withdrawal",
            identifier_kind=identifier_kind,
        ),
        Withdrawal,
    ):
        pytest.fail("Expected a typed testnet withdrawal response", pytrace=False)


async def test_private_testnet_withdrawal_quotas(
    private_pay: Client, private_live_call: LiveCall
) -> None:
    if not isinstance(
        await private_live_call(private_pay.withdrawals.quotas, quotas=True), WithdrawalQuotas
    ):
        pytest.fail("Expected a typed testnet withdrawal quotas response", pytrace=False)
