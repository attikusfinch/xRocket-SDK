# xRocket Python SDK — проектирование и первый срез

Python 3.11+. **Draft**, без публикации в PyPI. Поддерживается Current Pay API;
Exchange запланирован отдельным модулем того же пакета. Legacy API исследован
для сравнения, исполняемого Legacy-клиента нет.

## С чего начать чтение

- [Новая сессия: стартовый промпт и очередь задач](START.md)
- [Управляемый цикл: отдельные исполнители, review и Git](workflow/AUTOPILOT.md)
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
| `pay.invoices.create(request=InvoiceCreateRequest(...))` | `POST /api/v1/invoices` |
| `pay.invoices.delete(invoice_id=..., client_invoice_id=...)` | `DELETE /api/v1/invoice` |
| `pay.invoices.payments(invoice_id=..., client_invoice_id=..., cursor=..., limit=...)` | `GET /api/v1/invoice/payments` |
| `pay.cheques.list(...)` | `GET /api/v1/cheques` |
| `pay.cheques.retrieve(cheque_id=..., client_cheque_id=...)` | `GET /api/v1/cheque` |
| `pay.payouts.list(from_date=..., to_date=..., cursor=..., limit=...)` | `GET /api/v1/payouts` |
| `pay.payouts.retrieve(payout_id=..., client_payout_id=...)` | `GET /api/v1/payout` |
| `pay.withdrawals.list(from_date=..., to_date=..., status=..., cursor=..., limit=...)` | `GET /api/v1/withdrawals` |
| `pay.withdrawals.retrieve(withdrawal_id=..., client_withdrawal_id=...)` | `GET /api/v1/withdrawal` |
| `pay.withdrawals.quotas(network=..., asset=...)` | `GET /api/v1/withdrawal-quotas` |

Ответы типизированы, деньги читаются как `Decimal`. Списки возвращают одну страницу.
`pay.health.get()` доступен без токена и возвращает `Health` с типизированными
компонентами `HealthComponent` в `info`, `error`, `details`. Неизвестные статусы
и поля сохраняются. Асинхронный вызов — `await pay.health.get()`.
Status-only ответ также поддерживается: отсутствующие коллекции компонентов —
`None` (сведения неизвестны), переданные пустые коллекции — `[]`.
Явный `null` вместо переданной коллекции отвергается. Для сохранения missing
при сериализации используйте `health.model_dump(exclude_unset=True)`.
`invoices.payments()` возвращает одну `InvoicePaymentPage`; `pagination.next`
равен `None` на последней странице. Вложенные internal/blockchain транзакции
типизированы, неизвестный тип сохраняется как `UnknownInvoiceTransaction`.
Состояние завершения платежа определяется `finalized_at`, а не неизвестным status.
`invoices.create()` принимает отдельный `InvoiceCreateRequest` и возвращает `Invoice`
по HTTP 200. Request DTO доступны из `xrocket.pay` и `xrocket.pay.models`:
`InvoiceCreateRequest`, `InvoiceCallbackRequest`, `InvoiceURLRequest`, `InvoiceCustomerRequest`.
Суммы принимают Decimal/decimal string, `expires_in` — целое в миллисекундах, 0 сохраняется.
Пропущенные поля не отправляются, явный None для этих non-nullable request fields отвергается.
Нельзя одновременно передать `price_amount` и `min_payment`; отсутствие обеих допускается
по OAS, но принятие сервером не подтверждено (PAY-008). Request/response DTO не смешиваются.
`invoices.delete()` требует хотя бы один непустой строковый ID до 100 символов,
передаёт оба при наличии и возвращает None на пустой HTTP 200. Create client ID
не ограничен этими 100 символами. Live mutations в проверках проекта не выполнялись.
`cheques.list()` возвращает `CursorPage[Cheque]` и принимает `from_date` / `to_date`
как datetime с часовым поясом, парные `target_type` / `target`, `state`, `cursor`
и целочисленный `limit` от 1 до 1000. Даты передаются в ISO 8601 с исходным offset.
`cheques.retrieve()` требует хотя бы один непустой строковый ID длиной до 100
символов; если заданы оба, передаёт оба. В `Cheque` обязательны только `cheque_id`,
`asset`, `links`, `deleted`; ссылки внутри `links` и `state` необязательны.
Отменённый чек может читаться через retrieve с `deleted=True`; list исключает
отменённые чеки по контракту API. Поле суммы в Current ChequeResponseDto не описано.
`payouts.list()` возвращает одну `CursorPage[Payout]`; даты принимаются как datetime
с часовым поясом, cursor сохраняется буквально. `limit` принимает целое число;
его диапазон этот GET в OAS не задаёт, SDK оставляет проверку диапазона серверу.
`payouts.retrieve()` требует хотя бы один непустой строковый ID до 100 символов
и передаёт оба, если заданы оба. `Payout.amount` — точный `Decimal`, обязательные
`status` / `target_type` принимают неизвестные строки, `callback` необязателен.
`withdrawals.list()` возвращает одну `CursorPage[Withdrawal]` с такими же date/cursor/
limit правилами, как payouts. Фильтр `status` принимает `CREATED`, `COMPLETED`, `FAIL`.
В ответе status необязателен и допускает неизвестные строки с сохранением регистра.
`withdrawals.retrieve()` локально требует один из ID длиной 1–100 символов;
семантика сервера без ID не подтверждена (PAY-017). Create допускает client ID
до 150 символов, поэтому retrieve по всей этой длине не обещается (PAY-016).
`withdrawals.quotas(network="TON", asset="USDT")` требует оба аргумента и возвращает
`WithdrawalQuotas`: минимум и комиссия — Decimal, precision — обычное конечное
число int/float. SDK не округляет суммы при чтении.
HTTP ошибки сохраняют `status_code`, `problem`, `request_id`, `retry_after`;
последние два поля могут отсутствовать, серверный контракт их не гарантирует.
Автоповторов нет. Остальные write-методы и webhook verification пока
планируются. Пакет `xrocket.exchange` зарезервирован без клиента.

P008 добавил внутренний фундамент записи: общий sync/async transport для
POST/PUT/DELETE, отдельные request DTO и точную Decimal-сериализацию с aliases,
missing/null и явной политикой JSON/пустого ответа. P009 добавил create/delete invoice;
остальные Pay write методы добавляются отдельными задачами с offline проверками.

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
Отдельно можно явно запустить testnet smoke:

```powershell
$env:XROCKET_RUN_LIVE = '1'
.venv\Scripts\python.exe -m pytest -m live
```

Live harness содержит 40 sync/async cases для всех 15 GET: public currencies/rates/
health и private app/list/retrieve/payments/quotas. Private tests требуют только
явный `XROCKET_PAY_TESTNET_TOKEN`; без него пропускаются. ID для retrieve/payments
и network/asset для quotas задаются отдельно, не берутся из списка аккаунта.
Без `XROCKET_RUN_LIVE=1` сетевые tests пропускаются даже при наличии JWT;
обычный pytest исключает marker live даже при включённом флаге.

Переменные fixtures, команды и skips — в [плане проверок](spec/test-plan.md).
На Windows при WinError 10055 можно добавить
`-o asyncio_default_test_loop_scope=session`.
P007 подтвердила currencies/rates и обнаружила status-only health response
(PAY-018). P019 добавила поддержку отсутствующих component fields; первоначальный
failure и последующие проверки записаны в [журнале live](spec/live-verification.md).
Private GET не подтверждены без JWT.

## Основные источники

[Главная документации](https://docs.xrocket.exchange/) по-прежнему ссылается на
[Legacy Swagger](https://pay.xrocket.exchange/api). Для новой интеграции опираемся
на [Current Pay](https://docs.xrocket.exchange/api/pay/pay-api-overview),
[Current OpenAPI](https://pay.api.xrocket.exchange/api/docs-json) и проверенные
[адреса mainnet/testnet](https://docs.xrocket.exchange/api/pay/reference/pay-rest-api).
Схемы сохранены в репозитории; противоречия перечислены, исходные JSON не исправлялись.
