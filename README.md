# xRocket Python SDK — проектирование и первый срез

Python 3.11+. **Draft**, без публикации в PyPI. Поддерживается Current Pay API;
Exchange запланирован отдельным модулем того же пакета. Legacy API исследован
для сравнения, исполняемого Legacy-клиента нет.

## С чего начать чтение

- [Новая сессия: стартовый промпт и очередь задач](START.md)
- [Архитектура и границы Pay/Exchange](spec/architecture.md)
- [Исследование Stripe, OpenAI, Coinbase и CCXT](spec/sdk-comparison.md)
- [Pay: все 25 операций, контракты и проблемы документации](spec/pay-api.md)
- [План реализации и тестов](spec/test-plan.md)
- [Результаты фактических проверок](spec/verification.md)
- [Источники и зафиксированные OpenAPI](spec/openapi/README.md)

## Что уже работает

Одинаковые ресурсы у `PayClient` и `AsyncPayClient`:

| Метод SDK | Current Pay API |
|---|---|
| `pay.health.get()` | `GET /health` |
| `pay.app.info()` | `GET /api/v1/app-info` |
| `pay.app.balances()` | `GET /api/v1/balances` |
| `pay.currencies.list(kind=...)` | `GET /api/v1/currencies` |
| `pay.rates.get(base=..., assets=[...])` | `GET /api/v1/rates` |
| `pay.invoices.list(...)` | `GET /api/v1/invoices` |
| `pay.invoices.retrieve(invoice_id=..., client_invoice_id=...)` | `GET /api/v1/invoice` |
| `pay.invoices.payments(invoice_id=..., client_invoice_id=..., cursor=..., limit=...)` | `GET /api/v1/invoice/payments` |

Ответы типизированы, деньги читаются как `Decimal`. Списки возвращают одну страницу.
`pay.health.get()` доступен без токена и возвращает `Health` с типизированными
компонентами `HealthComponent` в `info`, `error`, `details`. Неизвестные статусы
и поля сохраняются. Асинхронный вызов — `await pay.health.get()`.
`invoices.payments()` возвращает одну `InvoicePaymentPage`; `pagination.next`
равен `None` на последней странице. Вложенные internal/blockchain транзакции
типизированы, неизвестный тип сохраняется как `UnknownInvoiceTransaction`.
Состояние завершения платежа определяется `finalized_at`, а не неизвестным status.
HTTP ошибки сохраняют `status_code`, `problem`, `request_id`, `retry_after`;
последние два поля могут отсутствовать, серверный контракт их не гарантирует.
Автоповторов нет. Запись, webhook verification и остальные Pay-ресурсы пока
описаны только в спеках. Пакет `xrocket.exchange` зарезервирован без клиента.

## Установка для разработки

```powershell
git clone https://github.com/attikusfinch/xRocket-SDK.git
cd xRocket-SDK
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.venv\Scripts\python.exe -m pytest
```

В текущем workspace проект уже находится в `F:\xrocket-pay\xrocket-sdk`; повторно
клонировать его туда не нужно. Локальная `.venv`, кэши, сборки, `.env`, ключи и
настройки редакторов исключены из Git; исходники, specs, lock и workflow сохраняются.

`requirements-dev.lock` фиксирует проверенное окружение Python 3.12 на Windows;
диапазоны поддерживаемых зависимостей указаны в `pyproject.toml`. На других
платформах можно установить `.venv\Scripts\python.exe -m pip install -e '.[dev]'`.

```python
import os

from xrocket.pay import PayClient

# Для публичных валют токен не нужен.
with PayClient(environment="testnet") as pay:
    currencies = pay.currencies.list(kind="crypto")

# Нужен JWT приложения с API Version = Current в testnet-боте.
with PayClient(
    api_token=os.environ["XROCKET_PAY_TESTNET_TOKEN"],
    environment="testnet",
) as pay:
    balances = pay.app.balances()
    page = pay.invoices.list(limit=100)
    if page.pagination.next is not None:
        next_page = pay.invoices.list(cursor=page.pagination.next, limit=100)
```

```python
from xrocket.pay import AsyncPayClient

async def main():
    async with AsyncPayClient(environment="testnet") as pay:
        rates = await pay.rates.get(base="USD", assets=["BTC", "ETH"])
        for rate in rates:
            print(rate.currency, rate.rate)
```

Токен передаётся явно и не читается автоматически из окружения.
Default `environment` — `mainnet`; примеры и сетевые smoke tests используют testnet.
`http_client=` позволяет внедрить `httpx.Client` / `httpx.AsyncClient`, который
остаётся во владении вызывающего кода. Timeout SDK по умолчанию 30 секунд;
redirects отключены. Используйте `with` / `async with` или `close()` / `aclose()`.

## Проверки

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m build --no-isolation
```

Unit tests используют `httpx.MockTransport`, сеть и API-токены не нужны.
Отдельно можно явно запустить публичный testnet smoke:

```powershell
$env:XROCKET_RUN_LIVE = '1'
.venv\Scripts\python.exe -m pytest -m live
```

Live tests делают только GET currencies/rates. Smoke 17.10.2026 подтвердил работу
testnet rates без токена с повторяющимися `assets=BTC&assets=ETH`.
Приватные testnet-операции без токена не проверяются.

## Основные источники

[Главная документации](https://docs.xrocket.exchange/) по-прежнему ссылается на
[Legacy Swagger](https://pay.xrocket.exchange/api). Для новой интеграции опираемся
на [Current Pay](https://docs.xrocket.exchange/api/pay/pay-api-overview),
[Current OpenAPI](https://pay.api.xrocket.exchange/api/docs-json) и проверенные
[адреса mainnet/testnet](https://docs.xrocket.exchange/api/pay/reference/pay-rest-api).
Схемы сохранены в репозитории; противоречия перечислены, исходные JSON не исправлялись.
