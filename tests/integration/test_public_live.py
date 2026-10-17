import os

import pytest

from xrocket.pay import AsyncPayClient, PayClient

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("XROCKET_RUN_LIVE") != "1", reason="Set XROCKET_RUN_LIVE=1"),
]


def test_public_testnet_currencies() -> None:
    with PayClient(environment="testnet", timeout=15) as pay:
        currencies = pay.currencies.list()
        assert currencies
        assert all(currency.code and currency.title for currency in currencies)


async def test_public_testnet_rates_without_auth() -> None:
    async with AsyncPayClient(environment="testnet", timeout=15) as pay:
        rates = await pay.rates.get(base="USD", assets=["BTC", "ETH"])
        assert {rate.currency for rate in rates} == {"BTC", "ETH"}
        assert all(rate.rate.is_finite() and rate.rate > 0 for rate in rates)
