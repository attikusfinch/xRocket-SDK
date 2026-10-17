# xRocket Python SDK — Current Pay

Python 3.11+, `xrocket-sdk` 0.1.0.dev0, **draft**, без публикации в PyPI.
Реализованы все 25 REST операций сохранённого Current Pay контракта и локальная
проверка/типизация webhooks. Exchange пока содержит только namespace; Legacy
клиента нет. Offline готовность Pay позволяет отдельно исследовать Exchange,
но не означает production verification или готовность денежных end-to-end сценариев.

- [Матрица 25 операций: API, owner, wire, tests и источники](spec/pay-operation-matrix.md)
- [Итоговый readiness ledger, 2026-10-18](spec/pay-readiness-2026-10-18.md)
- [Полный контракт, ограничения DTO и PAY-001–018](spec/pay-api.md)
- [Архитектура](spec/architecture.md), [план проверок](spec/test-plan.md)
- [Новая сессия](START.md), [очередь](workflow/tasks.json), [управляемый цикл](workflow/AUTOPILOT.md)
- История: [первый срез](spec/verification.md), [live testnet журнал](spec/live-verification.md)

## Public API

Одинаковые ресурсы у `PayClient` и `AsyncPayClient`; async вызовы используют `await`.

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
| `pay.invoices.create_payment_address(request=InvoiceCreatePaymentAddressRequest(...), invoice_id=...)` | `POST /api/v1/invoices/payments/address` |
| `pay.cheques.list(...)` | `GET /api/v1/cheques` |
| `pay.cheques.retrieve(cheque_id=..., client_cheque_id=...)` | `GET /api/v1/cheque` |
| `pay.cheques.create(request=ChequeCreateRequest(...))` | `POST /api/v1/cheques` |
| `pay.cheques.update(request=ChequeUpdateRequest(...), cheque_id=...)` | `PUT /api/v1/cheques` |
| `pay.cheques.delete(cheque_id=..., client_cheque_id=...)` | `DELETE /api/v1/cheques` |
| `pay.payouts.list(from_date=..., to_date=..., cursor=..., limit=...)` | `GET /api/v1/payouts` |
| `pay.payouts.retrieve(payout_id=..., client_payout_id=...)` | `GET /api/v1/payout` |
| `pay.payouts.create(request=PayoutCreateRequest(...))` | `POST /api/v1/payouts` |
| `pay.payouts.create_mass(request=MassPayoutCreateRequest(...))` | `POST /api/v1/mass-payouts` |
| `pay.withdrawals.create(request=WithdrawalCreateRequest(...))` | `POST /api/v1/withdrawals` |
| `pay.withdrawals.list(from_date=..., to_date=..., status=..., cursor=..., limit=...)` | `GET /api/v1/withdrawals` |
| `pay.withdrawals.retrieve(withdrawal_id=..., client_withdrawal_id=...)` | `GET /api/v1/withdrawal` |
| `pay.withdrawals.quotas(network=..., asset=...)` | `GET /api/v1/withdrawal-quotas` |
| `pay.withdrawal_links.create(request=WithdrawalLinkRequest(...))` | `POST /api/v1/withdrawal-link` |

Request/response DTO доступны из `xrocket.pay` и `xrocket.pay.models`; это те же
классы. Общие HTTP ошибки импортируются из `xrocket`, webhook ошибки — из
`xrocket.pay`. Ответы сохраняют неизвестные поля/строковые статусы. Строковые
суммы читаются как `Decimal`, суммы записи принимают конечный `Decimal` или
decimal string и отправляются точной JSON string без округления; float запрещён.
Response DTO автоматически не превращаются в request.

OAS документирует HTTP 200 для всех GET. Сохранённая политика `get()` принимает
любой 2xx, если body проходит проверку DTO. Write методы требуют точный 200,
кроме payment address (201); оба DELETE требуют строго пустой body на 200.
Неожиданный write 2xx или повреждённый success body вызывает `ResponseValidationError`.

## Установка для разработки

```powershell
git clone https://github.com/attikusfinch/xRocket-SDK.git
cd xRocket-SDK
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

В текущем workspace SDK уже находится в `F:\xrocket-pay\xrocket-sdk`.
`requirements-dev.lock` фиксирует проверенное Windows/Python 3.12 окружение;
диапазоны зависимостей — в `pyproject.toml`. Установка `.[dev]` по диапазонам
возможна отдельно; вся матрица версий ими не проверена. `.venv`, сборки, `.env`,
секреты и runtime координатора исключены из Git.

## Чтение и lifecycle

```python
import os
from xrocket.pay import PayClient

# Публичные GET не требуют JWT.
with PayClient(environment="testnet") as pay:
    health = pay.health.get()
    currencies = pay.currencies.list(kind="crypto")

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

async def read_rates():
    async with AsyncPayClient(environment="testnet") as pay:
        return await pay.rates.get(base="USD", assets=["BTC", "ETH"])
```

Полные исполнимые функции sync/async — в [examples/pay_read.py](examples/pay_read.py).
Импорт примеров не выполняет I/O. Environment у клиента по умолчанию **mainnet**;
во всех примерах задан testnet. SDK не читает token из окружения автоматически.
JWT должен относиться к testnet приложению с API Version = Current.

`with` / `async with`, `close()` / `aclose()` закрывают SDK-owned HTTP-сессию.
Переданный `http_client=` остаётся во владении вызывающего кода, его defaults
не меняются. SDK задаёт собственные auth и timeout (default 30 секунд), игнорирует
чужую default Authorization/auth handler, отключает redirects. После закрытия
SDK новые запросы запрещены. Собственная или внедрённая сессия переиспользуется;
автоматических retries, lookup, polling и pagination нет. Дополнительные политики
внешнего HTTP transport остаются ответственностью его владельца.

Все list методы читают одну страницу; конец — только `pagination.next is None`.
Cursor непрозрачен. Invoice payments возвращает отдельную `InvoicePaymentPage`
без total, известные internal/blockchain transactions типизированы, будущий type
сохраняется как `UnknownInvoiceTransaction`. List date filters принимают aware
`datetime`. Разные bounds limit/ID не унифицированы: см. [контракт](spec/pay-api.md).

`Health.info/error/details` при omission равны None (unknown); [] сохраняется,
explicit null отвергается. Отсутствующая error collection не доказывает отсутствие
ошибок. Для roundtrip missing используйте `model_dump(exclude_unset=True)`.

## Запись и неизвестный итог

```python
import os
from decimal import Decimal
from xrocket.pay import InvoiceCreateRequest, PayClient

# Стабильный ID сохранён приложением до I/O; выполнение создаёт testnet invoice.
with PayClient(
    api_token=os.environ["XROCKET_PAY_TESTNET_TOKEN"],
    environment="testnet",
) as pay:
    invoice = pay.invoices.create(request=InvoiceCreateRequest(
        price_currency="USDT",
        price_amount=Decimal("1.2500"),
        client_invoice_id=os.environ["XROCKET_PAY_TESTNET_CLIENT_INVOICE_ID"],
        expires_in=300_000,  # Current: миллисекунды; 0 также сохраняется.
    ))
```

[examples/pay_write.py](examples/pay_write.py) содержит те же sync/async функции
без top-level I/O. Они выполняют POST только при явном вызове. Проверки примеров
используют `MockTransport`, не создают invoices/переводы/выводы на сервере.

Optional request fields опускаются; explicit None для non-nullable полей
отвергается, пустые строки/списки/объекты/0 сохраняются. Extra inputs запрещены.
Invoice не допускает одновременно price_amount и min_payment; отсутствие обеих
локально разрешено по OAS, принятие сервером неизвестно (PAY-008).
Cheque password хранится как `SecretStr`, обычные repr/dumps маскируют его;
wire body содержит пароль явно. Не логируйте wire bytes. Surrogate code points
в request строках/ключах отвергаются до I/O; обычный Unicode/emoji сохраняется.

При timeout результат записи **неизвестен**: сервер мог выполнить операцию.
SDK не генерирует/заменяет client ID и не повторяет запрос. Сверка через явный
retrieve по сохранённому ID — отдельный GET; not-found не доказывает безопасность
replay. Для withdrawal create допускает client ID до 150, retrieve — только
1–100 (PAY-016/017); lookup длинного client ID не обещается.

В mass payout HTTP 200 может содержать частичные или полные item errors:
проверяйте `success_payouts`, `error_payouts`, `has_errors`, `is_partial`.
Порядок/дубликаты ответа сохраняются; позиционного matching нет. Сохраняйте
уникальные client IDs каждого item, не повторяйте весь batch автоматически.
Batch target_type ограничен `telegram_user_id` по prose при противоречивом enum;
реальный batch limit не известен (PAY-009/010). Withdrawal link возвращает ссылки
без открытия, даже все три ссылки могут отсутствовать; link не подтверждает вывод.

## Webhooks: исходные bytes до JSON

```python
import os
from xrocket.pay import (
    InvoiceWebhook, PaymentStatusChangedWebhookData, UnknownWebhook,
    WebhookError, WebhookPayloadError, verify_and_decode_webhook,
)

def receive(raw_body: bytes, headers):
    # HTTP adapter сохраняет исходные bytes и дубли заголовков либо отклоняет дубли.
    try:
        delivery = verify_and_decode_webhook(
            raw_body=raw_body,
            headers=headers,
            webhook_secret=os.environ["XROCKET_PAY_TESTNET_WEBHOOK_SECRET"],
        )
    except WebhookPayloadError:
        raise  # Подпись валидна; известный payload/JSON повреждён.
    except WebhookError:
        raise  # Отклонить; business processing не начинать.

    delivery_id = delivery.id  # Единственный ключ dedupe: верхний delivery id.
    # Приложение атомарно сохраняет dedupe + обработку в своём durable storage.
    if isinstance(delivery, UnknownWebhook):
        return delivery_id, None  # Будущий type/event не означает успех платежа.
    if isinstance(delivery, InvoiceWebhook) and isinstance(
        delivery.data, PaymentStatusChangedWebhookData
    ):
        payment = delivery.data.payment
        return delivery_id, payment.finalized_at is not None
    return delivery_id, None
```

Полный локальный decoder и finality helper — в [examples/pay_webhook.py](examples/pay_webhook.py).
Webhook secret — отдельный Webhook Token, **не JWT**. Current HMAC-SHA256 использует
точные bytes `Signature-Timestamp + b"." + raw_body`, direct secret и version v1;
Legacy hash transform не применяется. `verify_webhook_signature` доступен отдельно,
без JSON parsing; `verify_and_decode_webhook` сначала проверяет подпись и окно,
затем UTF-8/JSON/DTO. Прямые constructors DTO подпись не проверяют.

Default окно ±300000 ms включительно — настраиваемая политика SDK, не гарантия API.
Повторная доставка внутри окна снова валидна. Порядок событий не гарантируется;
SDK не хранит IDs. Dedupe, durable business processing и HTTP server принадлежат
приложению; invoice/payment/transaction IDs не заменяют верхний delivery id.

Unknown type/invoice event → `UnknownWebhook` с raw данными. Known malformed →
`WebhookPayloadError`. Неизвестные статусы сохраняются, успех из них не выводится.
Payment finality — `finalized_at is not None`, это не синоним paid; paid требует
проверки известного status отдельно. Известные вложенные даты требуют aware
date-time strings до coercion (включая finalizedAt); numeric epochs отвергаются.
Unknown/raw поля не интерпретируются. `raw_body`/`raw_payload` доступны явно;
обычный repr скрыт, dumps/raw/вложенные REST DTO могут содержать чувствительные данные.

## Ошибки

| Ошибка / import | Значение |
| --- | --- |
| `xrocket.AuthenticationError` | Нет требуемого JWT до I/O (status_code=None) или HTTP 401 |
| `xrocket.PermissionDeniedError` / `NotFoundError` / `RateLimitError` | HTTP 403 / 404 / 429 |
| `xrocket.ServerError` / `APIError` | HTTP ≥500 / прочие non-2xx, включая redirect |
| `xrocket.RequestTimeoutError` / `TransportError` | Timeout / другая ошибка HTTP transport |
| `xrocket.ResponseValidationError` | Невалидный success body или неожиданный write success status |
| `xrocket.pay.WebhookError` subclasses | Headers, signature, timestamp, configuration; payload error отдельно |
| `ValueError`, `TypeError`, Pydantic `ValidationError` | Локальная конфигурация/inputs до I/O |

`APIError` сохраняет `status_code`, object `problem`, optional `request_id` /
`retry_after`. Metadata не гарантирована сервером; не-JSON error сохраняет status,
problem остаётся {}. Raw response/body и произвольные headers не сохраняются.
Сообщения HTTP ошибок общие, но явный problem/transport `__context__` могут
содержать чувствительные данные. Webhook ошибки safe path очищают cause/context;
захват traceback locals сторонними средствами и явное логирование inputs не покрыты.
Retry-After не запускает автоматический retry. Duplicate client ID error не скрывается.

## Проверки и границы подтверждения

```powershell
.venv\Scripts\python.exe -m pytest -o asyncio_default_test_loop_scope=session
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m build --no-isolation
```

Session-loop override — workaround Windows WinError 10055; permanent config не меняется.
Offline tests используют синтетические fixtures, MockTransport и synthetic signing,
включая исполнение примеров. Сеть/секреты не нужны. [Ledger](spec/pay-readiness-2026-10-18.md)
фиксирует новый запуск отдельно от старых evidence и указывает непроверенные платформы.

Live GET opt-in: `XROCKET_RUN_LIVE=1` + `pytest -m live`; harness содержит 40 sync/async
cases для 15 GET. Private tests используют только явно настроенные testnet JWT/ID/quota
fixtures; отсутствие данных даёт independent skips. Обычный pytest исключает live
даже при выставленном флаге. Variables и gates — в [плане](spec/test-plan.md).

Исторически public testnet currencies/rates прошли, health сначала выявил PAY-018,
затем прошёл после P019. Private 34 skips без JWT/fixtures не являются подтверждением.
Новый P018 pass — только offline: live API, mutations/webhooks, mainnet, дедупликация,
replay/finality server guarantees и вся матрица Python/OS не проверялись.
Nullable overrides, precision/limit/4KB semantics и другие unresolved API facts —
в [PAY issues/open questions](spec/pay-api.md#12-открытые-вопросы-до-расширения-sdk).

## Источники

Сохранённые [Current/Legacy OAS и provenance](spec/openapi/README.md) задают контракт
этого среза; snapshots вручную не меняются и не объявляются текущим live API.
Официальные [Current overview](https://docs.xrocket.exchange/api/pay/pay-api-overview),
[REST reference](https://docs.xrocket.exchange/api/pay/reference/pay-rest-api) и
[Current OpenAPI](https://pay.api.xrocket.exchange/api/docs-json) перечислены как
источники snapshot. [Главная документации](https://docs.xrocket.exchange/) также
ссылается на [Legacy Swagger](https://pay.xrocket.exchange/api); Legacy auth/DTO/units
в Current не переносятся.
