from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from xrocket import pay
from xrocket.pay import Balance, Currency, CursorPage, Invoice, Rate, models
from xrocket.pay.models import Money


@pytest.mark.parametrize(
    "name",
    [
        "AppBalances",
        "AppInfo",
        "Balance",
        "Currency",
        "CurrencyNetwork",
        "CursorPage",
        "CursorPagination",
        "Invoice",
        "InvoiceCallback",
        "InvoiceCustomer",
        "InvoiceLinks",
        "InvoiceURL",
        "Rate",
    ],
)
def test_existing_model_imports_share_the_same_types(name: str) -> None:
    assert name in pay.__all__
    assert name in models.__all__
    assert getattr(pay, name) is getattr(models, name)


def test_money_remains_importable_from_models() -> None:
    amount = TypeAdapter(Money).validate_python("12345678901234567890.0000000001")
    assert amount == Decimal("12345678901234567890.0000000001")


@pytest.mark.parametrize("value", [0.1, True, float("nan"), "NaN", "Infinity", "-Infinity"])
def test_money_rejects_lossy_or_non_finite_values(value: object) -> None:
    with pytest.raises(ValidationError):
        Rate.model_validate({"currency": "BTC", "rate": value})


def test_decimal_precision_and_trailing_zeros_survive_json() -> None:
    balance = Balance.model_validate_json(
        '{"asset":"USDT","balance":"9999999999999999.0000000001",'
        '"available":"0.0000000001","holds":"9999999999999999.0000000000"}'
    )
    assert balance.balance == Decimal("9999999999999999.0000000001")
    assert balance.holds.as_tuple().exponent == -10
    assert '"9999999999999999.0000000001"' in balance.model_dump_json()


def test_minimal_invoice_optional_money_and_expiration() -> None:
    invoice = Invoice.model_validate(
        {
            "id": "inv-1",
            "priceCurrency": "USDT",
            "createdAt": "2026-10-17T00:00:00Z",
            "status": "partially_paid",
            "links": {"telegramBotLink": "https://t.me/xRocket?start=inv_1"},
        }
    )
    assert invoice.price_amount is None
    assert invoice.expires_at is None
    assert invoice.links.telegram_bot_link.startswith("https://t.me/")
    assert invoice.model_dump(by_alias=True)["priceCurrency"] == "USDT"


def test_currency_keeps_future_network_and_response_fields() -> None:
    currency = Currency.model_validate(
        {
            "code": "NEW",
            "title": "New asset",
            "kind": "future_kind",
            "networks": [{"code": "NEW_CHAIN", "confirmations": 7}],
            "future": True,
        }
    )
    assert currency.networks[0].code == "NEW_CHAIN"
    assert currency.networks[0].model_extra == {"confirmations": 7}
    assert currency.model_extra == {"future": True}


def test_shared_page_does_not_require_total() -> None:
    page = CursorPage[Invoice].model_validate({"items": [], "pagination": {"next": None}})
    assert page.pagination.total is None
    assert page.items == []


@pytest.mark.parametrize("field", ["createdAt", "expiresAt"])
def test_invoice_rejects_ambiguous_timezone(field: str) -> None:
    payload = {
        "id": "inv-1",
        "priceCurrency": "USDT",
        "createdAt": "2026-10-17T00:00:00Z",
        "status": "active",
        "links": {"telegramBotLink": "https://t.me/xRocket?start=inv_1"},
        field: "2026-10-17T00:00:00",
    }
    with pytest.raises(ValidationError):
        Invoice.model_validate(payload)
