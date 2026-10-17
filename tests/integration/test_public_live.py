"""Anonymous testnet GET smoke for both public client backends."""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from xrocket.pay import AsyncPayClient, PayClient

pytestmark = pytest.mark.live


async def test_public_testnet_currencies(
    public_pay: PayClient | AsyncPayClient, live_call: Callable[..., Awaitable[Any]]
) -> None:
    currencies = await live_call(public_pay.currencies.list)
    assert currencies
    assert all(currency.code and currency.title for currency in currencies)


async def test_public_testnet_rates_without_auth(
    public_pay: PayClient | AsyncPayClient, live_call: Callable[..., Awaitable[Any]]
) -> None:
    rates = await live_call(public_pay.rates.get, base="USD", assets=["BTC", "ETH"])
    assert {rate.currency for rate in rates} == {"BTC", "ETH"}
    assert all(rate.rate.is_finite() and rate.rate > 0 for rate in rates)


async def test_public_testnet_health(
    public_pay: PayClient | AsyncPayClient, live_call: Callable[..., Awaitable[Any]]
) -> None:
    health = await live_call(public_pay.health.get)
    assert health.status == "ok"
    if health.error is not None:
        assert not health.error
