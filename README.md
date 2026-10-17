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
`invoices.create_payment_address()` принимает `InvoiceCreatePaymentAddressRequest`
с обязательным `pay_network` (`TON`, `BSC`, `ETH`, `BTC`, `TRX`, `SOL`). Один или оба
ID длиной 1–100 передаются в query; body содержит только `payNetwork`.
Только HTTP 201 возвращает `InvoicePaymentAddress`: адрес, валюту, сеть и обязательный
`expires_at` с часовым поясом. Необязательный `min_amount` читается как Decimal;
при отсутствии равен None, явный null отвергается. Неизвестные response поля/сети
сохраняются. Async-вызов использует те же аргументы с `await`.

```python
from xrocket.pay import InvoiceCreatePaymentAddressRequest

# Uses an existing authenticated PayClient and an existing invoice ID.
address = pay.invoices.create_payment_address(
    invoice_id="existing-invoice-id",
    request=InvoiceCreatePaymentAddressRequest(pay_network="TON"),
)
print(address.address, address.expires_at, address.min_amount)
```

`cheques.list()` возвращает `CursorPage[Cheque]` и принимает `from_date` / `to_date`
как datetime с часовым поясом, парные `target_type` / `target`, `state`, `cursor`
и целочисленный `limit` от 1 до 1000. Даты передаются в ISO 8601 с исходным offset.
`cheques.retrieve()` требует хотя бы один непустой строковый ID длиной до 100
символов; если заданы оба, передаёт оба. В `Cheque` обязательны только `cheque_id`,
`asset`, `links`, `deleted`; ссылки внутри `links` и `state` необязательны.
Отменённый чек может читаться через retrieve с `deleted=True`; list исключает
отменённые чеки по контракту API. Поле суммы в Current ChequeResponseDto не описано.
`cheques.create()` принимает отдельный `ChequeCreateRequest` с обязательными `asset`
и `amount` (Decimal/decimal string), client ID до 50 символов и парными target fields.
`ChequeCallbackRequest` / `ChequeURLRequest` задают вложенные webhook/redirect параметры.
Все request DTO доступны из `xrocket.pay` и `xrocket.pay.models`, extra fields запрещены.
Password хранится как SecretStr: repr и обычные dumps маскируют значение; исходное
значение попадает только в подготовленный HTTP body. Не записывайте этот body в логи.
Surrogate code points в request строках/ключах отвергаются до I/O общим ValueError
без JSON/password в исключении; обычный Unicode и emoji поддерживаются.
`cheques.update(request=ChequeUpdateRequest(description=""), cheque_id=...)` очищает
описание; omission оставляет его без изменения, explicit None запрещён.
Update поддерживает только description. Update/delete требуют ID длиной 1–100,
передают оба при наличии. Все три mutation paths plural; create/update возвращают
Cheque только на HTTP 200, delete — None на строго пустой HTTP 200.
`payouts.list()` возвращает одну `CursorPage[Payout]`; даты принимаются как datetime
с часовым поясом, cursor сохраняется буквально. `limit` принимает целое число;
его диапазон этот GET в OAS не задаёт, SDK оставляет проверку диапазона серверу.
`payouts.retrieve()` требует хотя бы один непустой строковый ID до 100 символов
и передаёт оба, если заданы оба. `Payout.amount` — точный `Decimal`, обязательные
`status` / `target_type` принимают неизвестные строки, `callback` необязателен.
`payouts.create()` принимает отдельный `PayoutCreateRequest` с обязательными
`target` (до 100 символов), `target_type` (`user_id`, `telegram_user_id`,
`telegram_username`), `asset` и `amount` (Decimal/decimal string → точная JSON string).
Необязательны `client_payout_id` (до 50 символов), `description` без ограничения
длины в schema и `PayoutCallbackRequest(callback_url=..., payload=...)`;
callback URL — до 500 символов, payload — JSON object. DTO доступны из обоих
public model import paths. Пропущенные поля не отправляются, explicit None запрещён.
HTTP 200 возвращает `Payout`; async использует те же аргументы с `await`.

Сохраните стабильный client ID до отправки payout. SDK не создаёт и не меняет
его, duplicate API error передаётся вызывающему коду. `RequestTimeoutError`
означает неизвестный итог: выплата могла быть создана. SDK делает одну HTTP
попытку без автоматического lookup или повтора. После timeout выполните явный
`pay.payouts.retrieve(client_payout_id=saved_id)` (в async — с `await`) для сверки.
Это отдельный GET; not-found сам по себе не доказывает безопасность повторной
выплаты. Срок и scope дедупликации сервером не подтверждены.

`payouts.create_mass()` принимает `MassPayoutCreateRequest(asset=..., payouts=[...])`.
Внутри — отдельные `MassPayoutItemRequest` без asset: обязательны `target`,
`target_type="telegram_user_id"` и точный `amount`; client ID, description и
`PayoutCallbackRequest` необязательны с теми же omission/null правилами.
Для batch разрешён только Telegram user ID по описанию операции: более широкий
OAS enum противоречит prose и пока не подтверждён (PAY-010). Локального лимита
размера batch нет: ошибочный `maxLength: 500` на object не задаёт `maxItems`
(PAY-009). Принятие сервером пустого или большого batch не подтверждено.

HTTP 200 возвращает `MassPayoutResult`: `success_payouts` содержит `Payout`,
`error_payouts` — `MassPayoutError` с typed `MassPayoutErrorReason`.
`result.has_errors` отмечает наличие ошибок, `result.is_partial` — смесь успехов
и ошибок. Проверяйте оба массива, в том числе когда все items завершились ошибкой.
Все DTO публичны из `xrocket.pay` и `xrocket.pay.models`; async использует `await`.

Сохраните отдельный стабильный client ID каждого item до отправки. IDs, ведущие
нули, порядок и дубликаты в каждом массиве ответа сохраняются. Позиции ответа
не сопоставляются с request: API не обещает общий порядок и не даёт index для
ошибок. Без уникальных client IDs однозначная корреляция не гарантируется.
SDK делает один POST без разбиения, параллельных single payouts, lookup или
автоповтора. Успешные items не повторяются. После timeout исход каждого item
неизвестен; сверяйте его отдельно по сохранённому ID. Не повторяйте весь batch
по факту частичной ошибки; безопасная семантика replay не подтверждена live.

`withdrawals.create()` принимает отдельный `WithdrawalCreateRequest`: обязательны
`client_withdrawal_id` (до 150 символов), `network` (`TON`, `BSC`, `ETH`, `BTC`,
`TRX`, `SOL`), `address` (до 100 символов), `asset` и `amount` (Decimal/decimal
string → точная JSON string). Network задаётся явно, default из OAS не подставляется.
Необязательны `comment` до 50 символов и `WithdrawalCallbackRequest` с optional
`callback_url` до 500 символов / `payload` (JSON object). DTO доступны из
`xrocket.pay` и `xrocket.pay.models`. Пропущенные поля не отправляются, explicit
None и extra fields запрещены. SDK не нормализует адреса, asset или comment,
не округляет и не обрезает amount. HTTP 200 возвращает существующий `Withdrawal`;
асинхронный вызов использует те же аргументы с `await`.

Сохраните стабильный непустой client ID до отправки. SDK требует поле и сохраняет
значение без генерации, замены или усечения; OAS не задаёт minLength, принятие
пустой строки сервером не подтверждено. Для последующего lookup по client ID
выбирайте длину 1–100: create допускает 101–150, но retrieve такой ID отвергнет
локально (PAY-016). При успешном create можно сохранить `result.withdrawal_id`
для явного retrieve. После `RequestTimeoutError` итог неизвестен: withdrawal мог
быть создан, это не подтверждённый отказ перевода. SDK делает ровно одну HTTP
попытку без retry, lookup или polling. Для сверки используйте отдельный retrieve
по сохранённому ID в его диапазоне; lookup по длинному client ID не обещается.
Not-found не доказывает безопасность повтора; дедупликация/replay не подтверждены live.

`withdrawals.list()` возвращает одну `CursorPage[Withdrawal]` с такими же date/cursor/
limit правилами, как payouts. Фильтр `status` принимает `CREATED`, `COMPLETED`, `FAIL`.
В ответе status необязателен и допускает неизвестные строки с сохранением регистра.
`withdrawals.retrieve()` локально требует один из ID длиной 1–100 символов;
семантика сервера без ID не подтверждена (PAY-017). Create допускает client ID
до 150 символов, поэтому retrieve по всей этой длине не обещается (PAY-016).
`withdrawals.quotas(network="TON", asset="USDT")` требует оба аргумента и возвращает
`WithdrawalQuotas`: минимум и комиссия — Decimal, precision — обычное конечное
число int/float. SDK не округляет суммы при чтении.

`withdrawal_links.create()` принимает отдельный `WithdrawalLinkRequest` с обязательными
`network` (`TON`, `BSC`, `ETH`, `BTC`, `TRX`, `SOL`), `address` до 100 символов,
`asset` и точным `amount` (Decimal/decimal string → JSON string). Network задаётся
явно. Необязательны `comment` до 50 символов и строковый `platform`: задавайте
platform только если его предоставил xRocket. Пропущенные поля опускаются,
explicit None запрещён. Client ID и callback в этот запрос не входят.
HTTP 200 возвращает `WithdrawalLink` с необязательными `telegram_bot_link`,
`telegram_mini_app_link`, `web_link`. Все ссылки могут отсутствовать, в Python
это None; для сохранения omission используйте `model_dump(exclude_unset=True)`.
Присутствующие ссылки должны быть строками: explicit null отвергается по OAS,
проверки URL и нормализации нет, неизвестные response поля сохраняются.
Обе модели доступны из `xrocket.pay` и `xrocket.pay.models`; async использует
те же аргументы с `await`. SDK возвращает ссылки без открытия; это отдельная
операция Current, отличная от `withdrawals.create()` и Legacy GET.
После timeout создание ссылки остаётся неизвестным, автоматического повтора нет.

HTTP ошибки сохраняют `status_code`, `problem`, `request_id`, `retry_after`;
последние два поля могут отсутствовать, серверный контракт их не гарантирует.
Автоповторов нет. Все 25 Current Pay REST операций реализованы. Stateless проверка
Current webhook доступна отдельно от клиентов, включая typed events и unknown fallback.
Пакет `xrocket.exchange` зарезервирован без клиента.

```python
from xrocket.pay import WebhookError, verify_webhook_signature

# raw_body: исходные bytes HTTP запроса; headers: mapping имён/строковых значений.
# webhook_secret получен отдельно из Webhook Token, это не JWT API token.
try:
    verify_webhook_signature(
        raw_body=raw_body,
        headers=headers,
        webhook_secret=webhook_secret,
        tolerance_ms=300_000,
    )
except WebhookError:
    ...  # Отклонить запрос; JSON и business processing ещё не выполнялись.
else:
    ...  # Теперь приложение может разбирать исходный raw_body как JSON.
```

Подпись — Current HMAC-SHA256 от точных ASCII bytes `Signature-Timestamp`, точки
и исходного body. Verifier не декодирует/не пересериализует JSON. Secret str кодируется
UTF-8 без trimming/hash, bytes используются без изменения; пустой secret запрещён.
Имена заголовков нечувствительны к регистру; значения не нормализуются. Timestamp —
непустые ASCII digits в ms (ведущие нули сохраняются в подписи), version — ровно `v1`,
signature — 64 hex digits любого регистра. Дубли signing headers отвергаются;
адаптер HTTP должен сохранять дубли либо отклонять их до превращения в mapping.

По умолчанию допустима разница с часами ±300 000 ms включительно. `tolerance_ms`
принимает целое ≥0 без bool; 0 требует точного совпадения. `clock=lambda: now_ms`
позволяет передать тестовые часы (целые неотрицательные Unix ms), по умолчанию
используются системные часы. Подпись проверяется раньше часов/окна. Окно — политика
SDK, не гарантия API о clock skew или retries. Stateless verifier возвращает None
при успехе или поднимает `WebhookError`: `WebhookHeaderError`, `WebhookSignatureError`,
`WebhookTimestampError`, `WebhookConfigurationError` (доступны из `xrocket.pay`).
Ошибка не сохраняет входные значения в args/атрибутах/cause/context. Обычное
форматирование ошибки не раскрывает secret/body; сторонний сбор traceback locals
или явное логирование аргументов остаётся ответственностью приложения.
Повторный валидный webhook внутри окна снова пройдёт проверку; dedupe по delivery
`id` и HTTP server остаются приложению. Для typed parsing доступен безопасный путь ниже.

Для типизированного разбора используйте `verify_and_decode_webhook`: он вызывает
тот же verifier **до** UTF-8/JSON parsing и проверки DTO. После успешной подписи
невалидный payload даёт отдельный `WebhookPayloadError`; неизвестная строка type
или invoice event возвращает `UnknownWebhook` с доступным raw payload.

```python
from xrocket.pay import (
    InvoiceWebhook,
    PaymentStatusChangedWebhookData,
    UnknownWebhook,
    WebhookPayloadError,
    verify_and_decode_webhook,
)

try:
    delivery = verify_and_decode_webhook(
        raw_body=raw_body, headers=headers, webhook_secret=webhook_secret,
    )
except WebhookPayloadError:
    ...  # Подпись и окно проверены, но JSON/известный payload повреждён.
else:
    delivery_id = delivery.id  # Ключ dedupe приложения, не invoice.id/payment.id.
    if isinstance(delivery, UnknownWebhook):
        original_payload = delivery.raw_payload  # Явный доступ; может быть чувствительным.
    elif isinstance(delivery, InvoiceWebhook):
        if isinstance(delivery.data, PaymentStatusChangedWebhookData):
            payment = delivery.data.payment
            is_final = payment.finalized_at is not None
            # status сохраняется точно; неизвестный status не означает paid/failed.
```

Ошибки подписи/headers/окна/config остаются прежними `WebhookError` subclasses.
Invoice-only `InvoiceStatusChangedWebhookData` не требует payment. `ChequeWebhook`,
`PayoutWebhook`, `WithdrawalWebhook` содержат в data существующие Pay DTO.
Все envelope и invoice data DTO, `UnknownWebhook`, union `WebhookEvent` доступны
через `xrocket.pay` и `xrocket.pay.models`. Поля/статусы будущих версий сохраняются.
Envelope timestamp — aware datetime из JSON date-time string; signing timestamp
в заголовке проверяется отдельно. JSON fractional numbers разбираются как Decimal
без float; duplicate object keys и NaN/Infinity отвергаются политикой SDK.

`raw_body` возвращает исходные проверенные bytes, `raw_payload` — отдельную копию
JSON snapshot с исходными wire keys и Decimal. Мутации DTO не меняют snapshot.
Обычные repr/str envelope и invoice data скрывают все поля/extras; явные dumps,
raw свойства и доступ к вложенным REST DTO могут раскрыть чувствительные данные.
Ошибки безопасного пути не содержат body/secret в messages/args/cause/context.
Прямые DTO constructors/model_validate **не проверяют подпись** и не заполняют
raw snapshots; попытка прочитать их raw свойства даёт RuntimeError.
Повторные/out-of-order доставки допускаются: SDK не хранит delivery IDs и не
обещает порядок. Dedupe storage и HTTP server остаются приложению.

P008 добавил внутренний фундамент записи: общий sync/async transport для
POST/PUT/DELETE, отдельные request DTO и точную Decimal-сериализацию с aliases,
missing/null и явной политикой JSON/пустого ответа. P009 добавил create/delete invoice,
P010 — создание invoice payment address, P011 — create/update/delete cheques,
P012 — создание одиночного payout, P013 — mass payouts с отдельными успехами/ошибками,
P014 — создание withdrawal с обязательным caller ID, P015 — создание withdrawal link.
Write операции проверены offline, без реальных денежных действий.

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
