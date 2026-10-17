# xRocket Pay: контракт Python SDK

Статус: исследование контракта и спецификация первого read-only среза, 2026-10-17. Первый поддерживаемый API — **Pay Current**. Exchange будет отдельным модулем SDK. Legacy сохранён как источник миграционных различий, его поддержка в первый срез не входит.

## 1. Источники и приоритет

- [Официальная документация](https://docs.xrocket.exchange/).
- [Pay REST API: окружения и narrative reference](https://docs.xrocket.exchange/api/pay/reference/pay-rest-api).
- [Pay Current overview](https://docs.xrocket.exchange/api/pay/pay-api-overview).
- [Миграция Legacy → Current](https://docs.xrocket.exchange/api/pay/migration-legacy).
- Локальный живой snapshot Current: [openapi/pay-current.json](openapi/pay-current.json), OpenAPI 3.0.0, API info.version `1.0.0`.
- Локальный живой snapshot Legacy: [openapi/pay-legacy.json](openapi/pay-legacy.json), API info.version `1.3.1`.

Приоритет по конкретному HTTP-пути, полям, response shapes и кодам ответа — сохранённый Current OpenAPI, затем подтверждённый ответ соответствующего живого окружения, затем narrative reference. Подтверждённые противоречия фиксируем как отдельные overrides с fixture; исходный snapshot не исправляем вручную. Narrative содержит устаревшие названия вроде transfer вместо payout, поэтому из неё нельзя механически переносить пути в SDK.

Для base URL используем официальный reference: Current snapshot содержит `servers: []` и сам не задаёт адрес сервера. При расхождении фиксируем источник конкретного утверждения, а не считаем один документ безошибочным во всём.

В Current snapshot **18 path keys, 25 HTTP operations, 61 component schema**. В Legacy — **15 path keys, 20 HTTP operations, 43 component schema**. Эти числа включают health/version endpoints.

JSON pointers ниже относятся к `openapi/pay-current.json`, если явно не указан Legacy. В pointers символ `/` внутри имени path экранирован как `~1`.

## 2. Окружения и аутентификация

| Окружение | Pay Current base URL |
| --- | --- |
| Mainnet | `https://pay.api.xrocket.exchange/` |
| Testnet | `https://pay.api.testnet.xrocket.exchange/` |

Адреса подтверждены [официальным Pay REST API reference](https://docs.xrocket.exchange/api/pay/reference/pay-rest-api). Пути ниже уже содержат `/api/v1`; нельзя добавить prefix второй раз. `GET /health` находится вне `/api/v1`.

Current использует JWT токен приложения:

```http
Authorization: Bearer <token>
```

Источник: `#/components/securitySchemes/bearer` и `#/info/description`. Приложение в боте должно иметь API Version = Current. SDK не декодирует JWT для принятия решений об авторизации и не обновляет токен самостоятельно: API здесь описывает получение/регенерацию токена через настройки приложения в боте.

`GET /api/v1/currencies` и `GET /health` не имеют operation security. Для `GET /api/v1/rates` summary обещает optional auth, но `security: [{"bearer": []}]` формально требует токен; это открытое противоречие. SDK должен уметь вызывать публичные методы без токена. Неподтверждённую optional-auth семантику rates покрываем отдельно и не объявляем scheme однозначным.

Проверка 17.10.2026: публичный GET testnet rates без токена с `base=USD&assets=BTC&assets=ETH` вернул ожидаемые курсы BTC и ETH. Для этого запроса optional auth и повторяющиеся query keys подтверждены живым сервером. Противоречие OAS сохраняется; mainnet, остальные assets и invoice ids этим тестом не проверялись. См. [verification.md](verification.md).

Legacy использует `Rocket-Pay-Key`, а его snapshot указывает production `https://pay.xrocket.exchange/`: Legacy `#/components/securitySchemes/api-key`, `#/servers/0/url`. Этот адрес не переносим в настройки Current.

Токены и webhook secrets не выводим в repr, exception messages, примеры и HTTP-логи. Это разные значения с разным назначением.

## 3. Полный inventory Current

Имена Python ниже задают удобные группы SDK; wire paths остаются ровно такими, как в OAS. Первые реализуемые методы закреплены: `app.info()`, `app.balances()`, `currencies.list()`, `rates.get(base=..., assets=...)`, `invoices.list()`, `invoices.retrieve()`. Остальные имена ресурса — план следующего этапа, а не обещание уже доступного API.

Все тела запросов в таблице — JSON `application/json`. Все перечисленные success responses с телом — `application/json`. Для DELETE success schema отсутствует; клиент должен принимать пустое тело.

| № | Группа | Метод и путь | Вход | Success | Документированные ошибки HTTP |
| --- | --- | --- | --- | --- | --- |
| 1 | health | `GET /health` | — | `200` health object | не перечислены |
| 2 | app | `GET /api/v1/app-info` | — | `200 AppResponseDto` | 401, 500 |
| 3 | app | `GET /api/v1/balances` | — | `200 AppBalancesResponseDto` | 401, 500 |
| 4 | invoices | `POST /api/v1/invoices` | body `InvoiceCreateRequestDto` | `200 InvoiceDto` | 400, 401, 404, 429, 500 |
| 5 | invoices | `GET /api/v1/invoices` | query: asset, fiat, ids, status, cursor, limit | `200 InvoiceListResponseDto` | 401, 429, 500 |
| 6 | invoices | `GET /api/v1/invoice` | invoiceId / clientInvoiceId | `200 InvoiceDto` | 400, 401, 404, 429, 500 |
| 7 | invoices | `DELETE /api/v1/invoice` | invoiceId / clientInvoiceId | `200`, response schema отсутствует | 400, 401, 404, 429, 500 |
| 8 | invoices/payments | `GET /api/v1/invoice/payments` | invoiceId / clientInvoiceId, cursor, limit | `200 InvoicePaymentListResponseDto` | 400, 401, 404, 429, 500 |
| 9 | cheques | `POST /api/v1/cheques` | body `ChequeCreateRequestDto` | `200 ChequeResponseDto` | 400, 401, 403, 404, 429, 500 |
| 10 | cheques | `GET /api/v1/cheques` | fromDate, toDate, targetType, target, state, cursor, limit | `200 ChequeListResponseDto` | 401, 429, 500 |
| 11 | cheques | `PUT /api/v1/cheques` | chequeId / clientChequeId; body `ChequeUpdateRequestDto` | `200 ChequeResponseDto` | 400, 401, 404, 429, 500 |
| 12 | cheques | `DELETE /api/v1/cheques` | chequeId / clientChequeId | `200`, response schema отсутствует | 400, 401, 404, 429, 500 |
| 13 | cheques | `GET /api/v1/cheque` | chequeId / clientChequeId | `200 ChequeResponseDto` | 400, 401, 404, 429, 500 |
| 14 | payouts | `POST /api/v1/payouts` | body `AppPayoutCreateRequestDto` | `200 AppPayoutResponseDto` | 400, 401, 403, 404, 429, 500 |
| 15 | payouts | `GET /api/v1/payouts` | fromDate, toDate, cursor, limit | `200 AppPayoutListResponseDto` | 400, 401, 429, 500 |
| 16 | payouts | `GET /api/v1/payout` | payoutId / clientPayoutId | `200 AppPayoutResponseDto` | 400, 401, 404, 429, 500 |
| 17 | withdrawals | `POST /api/v1/withdrawals` | body `WithdrawalCreateRequestDto` | `200 WithdrawalResponseDto` | 400, 401, 403, 404, 429, 500 |
| 18 | withdrawals | `GET /api/v1/withdrawals` | fromDate, toDate, status, cursor, limit | `200 WithdrawalListResponseDto` | 401, 429, 500 |
| 19 | withdrawals | `GET /api/v1/withdrawal` | withdrawalId / clientWithdrawalId | `200 WithdrawalResponseDto` | 401, 404, 429, 500 |
| 20 | withdrawals | `GET /api/v1/withdrawal-quotas` | **required** network, asset | `200 WithdrawalQuotasResponseDto` | 401, 429, 500 |
| 21 | withdrawal_links | `POST /api/v1/withdrawal-link` | body `WithdrawalLinkRequestDto` | `200 WithdrawalLinkResponseDto` | 400, 401, 404, 429, 500 |
| 22 | payouts | `POST /api/v1/mass-payouts` | body `MassPayoutsCreateRequestDto` | `200 MassPayoutsCreateResponseDto` | 400, 401, 403, 429, 500 |
| 23 | currencies | `GET /api/v1/currencies` | optional kind | `200 CurrencyResponseDto[]` | 429, 500 |
| 24 | rates | `GET /api/v1/rates` | optional base, assets | `200 RateResponseDto[]` | 404, 429, 500 |
| 25 | invoices/payment_addresses | `POST /api/v1/invoices/payments/address` | invoiceId / clientInvoiceId; body `InvoiceCreatePaymentAddressRequestDto` | **`201 InvoicePaymentAddressResponseDto`** | 400, 401, 403, 404, 429, 500 |

Важные особенности маршрутов: singular `/invoice`, `/cheque`, `/payout`, `/withdrawal` для retrieve; update/delete cheque используют plural `/cheques`. Нельзя выводить путь из правила единственного/множественного числа. Для большинства POST success равен 200, для payment address — 201; decoder должен учитывать контракт конкретной операции.

## 4. Первый read-only срез

Цель — доказать пригодность общего transport, auth, сериализации параметров, ошибок и моделей, прежде чем реализовывать создание счетов и движение средств.

### `app.info()`

`GET /api/v1/app-info` → объект с обязательными `id: str`, `name: str`. Источник: `#/components/schemas/AppResponseDto`. Балансов и `feePercents` здесь нет.

### `app.balances()`

`GET /api/v1/balances` → `{"balances": [...]}`. Каждый элемент обязательно содержит `asset`, `balance`, `available`, `holds`, все четыре поля — wire strings. Денежные поля преобразуем в `Decimal` напрямую из строки, asset сохраняем строкой. Не превращаем collection в словарь по asset: OAS этого не обещает.

Источники: `#/components/schemas/AppBalancesResponseDto`, `#/components/schemas/AppBalanceResponseDto`.

### `currencies.list(kind=None)`

`GET /api/v1/currencies`; `kind` принимает `crypto` или `fiat`. Ответ — массив, без success/data wrapper. У элемента обязательны `code`, `title`, `kind`, `networks`; каждый network содержит обязательный `code`. В snapshot известны TON, BSC, ETH, BTC, TRX, SOL.

Источники: `#/paths/~1api~1v1~1currencies/get/parameters`, `#/components/schemas/CurrencyResponseDto`, `#/components/schemas/CurrencyNetworkResponseDto`.

### `rates.get(base=None, assets=None)`

`GET /api/v1/rates`; у `base` в OAS указан default `USD`. `assets` — массив строк. Ответ — массив объектов с обязательными `currency: str`, `rate: str`; в SDK rate — `Decimal`. В ответе base не дублируется, поэтому он относится к контексту запроса.

Источник: `#/paths/~1api~1v1~1rates/get`, `#/components/schemas/RateResponseDto`. Optional auth требует отдельного подтверждения.

### `invoices.list(...)`

Query:

- `asset`, `fiat`, `status`, `cursor` — строки;
- `ids` — массив строк;
- `limit` — OAS number, maximum 1000, example 100; minimum/default отсутствуют.

Python-имена `snake_case` преобразуются в wire aliases явно. `None` означает отсутствие параметра; пустую строку, `0`, пустой массив нельзя автоматически терять через truthiness. Для array query OAS не задаёт `style`/`explode`: используем default form/explode, то есть повторяющиеся ключи, и проверяем совместимость smoke-тестом.

Ответ: `{"items": [Invoice], "pagination": {"total": number, "next": str | null}}`. В snapshot `total` назван number, по смыслу это счётчик; способ строгой integer-валидации должен быть согласован с живыми fixtures.

Источники: `#/paths/~1api~1v1~1invoices/get/parameters`, `#/components/schemas/InvoiceListResponseDto`, `#/components/schemas/CursorPaginationResponseDto`.

### `invoices.retrieve(invoice_id=None, client_invoice_id=None)`

`GET /api/v1/invoice`. Хотя оба query parameter помечены optional, нужен хотя бы один идентификатор. Если переданы оба, сервер использует `invoiceId`. SDK сохраняет эту семантику; не вводит запрет на оба значения. Максимальная длина каждого query identifier — 100.

Источник: `#/paths/~1api~1v1~1invoice/get/parameters/0`, `#/paths/~1api~1v1~1invoice/get/parameters/1`.

Минимальный обязательный `Invoice`: `id`, `priceCurrency`, `createdAt`, `status`, `links`. В `links` обязателен `telegramBotLink`; `telegramMiniAppLink` и `webLink` необязательны. Остальные invoice поля из snapshot необязательны: `priceAmount`, `minPayment`, `payCurrencies`, `clientInvoiceId`, `description`, `expiresIn`, `expiresAt`, `callback`, `url`, `customer`. Не делать сумму обязательной для open-amount invoice.

Источники: `#/components/schemas/InvoiceDto`, `#/components/schemas/InvoiceLinkDto`.

## 5. Деньги, время, идентификаторы и эволюция schema

### Деньги

Current передаёт суммы, balances, rates и fees строками. Публичные Python-модели используют `Decimal`; для будущих write methods допускаем `Decimal` и корректную decimal string, сериализуем в JSON string. Не используем binary float как промежуточный формат, не округляем без явного правила API и не считаем все активы имеющими одинаковую precision.

Примеры wire money: `AppBalanceResponseDto.balance/available/holds`, `InvoiceDto.priceAmount/minPayment`, `InvoicePaymentDto.payAmount/receiveAmount`, `RateResponseDto.rate`, `WithdrawalQuotasResponseDto.withdrawMinSize/withdrawFee`. `WithdrawalQuotasResponseDto.precision` — отдельное числовое поле, а не сумма.

### Время и отсутствующие значения

`createdAt` и прочие `date-time` представляем timezone-aware datetime, сохраняя смысл offset. `expiresIn` Current измеряется **в миллисекундах**, включая invoice create default 3600000; `0` означает отсутствие expiration. Legacy `expiredIn` измеряется в секундах.

Отличаем missing и явный null там, где это влияет на запросы. На response стороне учитываем документированные null вопреки ошибкам OAS, перечисленным ниже. Не превращаем объектные `date-time` типы из ошибочной схемы в пользовательский dict API.

### Идентификаторы

Current invoice IDs и прочие ID — строки. Не приводим строковые ID к int, не удаляем ведущие нули и не ограничиваем формат числовыми символами. Telegram IDs в Current customer/payer и target также передаются строками.

### Статусы и новые поля

| Объект | Известные значения |
| --- | --- |
| Invoice.status | active, paid, partially_paid, expired, cancelled |
| InvoicePayment.status | pending, paid, expired, failed, cancelled |
| Transaction.status / blockchain tx.status | pending, confirming, confirmed, failed |
| Cheque.state | active, completed, draft, error |
| Payout.status | finished, pending, failed |
| Withdrawal.status | CREATED, COMPLETED, FAIL |
| TargetType | user_id, telegram_user_id, telegram_username |
| Network | TON, BSC, ETH, BTC, TRX, SOL |

Регистр значим: withdrawal statuses uppercase, payout statuses lowercase. Response status/event принимают неизвестные строки; документация явно предупреждает о расширении invoice/payment/transaction statuses и webhook events. Известные константы могут помогать пользователю, но закрытый Python Enum не должен ломать decode неизвестного response. Не считать unknown status эквивалентом paid/failed. Unknown payment/transaction status трактуется как in progress согласно prose, а finality payment определяется `finalizedAt != null`.

Неизвестные response fields сохраняем или допускаем без ошибки валидации. Нельзя отправлять их обратно в write request автоматически. Входные request enums и response enum evolution — разные решения; ограничения request берём из контракта соответствующего метода.

## 6. Пагинация и коллекции

Основные коллекции invoices, cheques, payouts, withdrawals имеют `items` и `pagination: {total, next}`. `next` nullable, но required. `next: null` означает конец. Cursor — непрозрачная строка; его не декодируем, не конструируем из ID и не заменяем offset.

Invoice payments отличаются: `InvoicePaymentListResponseDto` содержит `pagination: {next}` без total. Generic page abstraction не должна требовать total у всех response типов. Нельзя определять конец только по `len(items) < limit`: сервер даёт явный next cursor.

В первом срезе метод `list()` возвращает одну страницу с доступной pagination. Автопагинация может быть отдельным helper после проверки cursor semantics. Любой iterator должен иметь защиту от повторяющегося cursor и не запускать бесконечный цикл при неконсистентном сервере.

Источники: `#/components/schemas/CursorPaginationResponseDto`, `#/components/schemas/InvoicePaymentListPaginationDto`, `#/components/schemas/InvoicePaymentListResponseDto`.

## 7. Ошибки и retry semantics

Current errors описаны problem objects с обязательными `type`, `title`, `status`, `detail`, `instance`, `kind`; дополнительно может присутствовать `info`. Media type в OAS — `application/json`; decoder не должен требовать только `application/problem+json`.

`type` — строка вида `/api/problems/invoice_not_found`. `kind` — более широкая категория; встречаются `client_data_validation`, `validation`, `authentication`, `authorization`, `unauthorized`, `forbidden`, `not_found`, `conflict`, `rate_limit`, `internal`. Оба поля сохраняем. HTTP status доступен независимо от наличия/качества JSON body.

Для первого среза:

| Метод | Problem types помимо общих internal/rate-limit |
| --- | --- |
| app.info, app.balances | 401 `/api/problems/unauthorized`; 500 `/api/problems/internal_error` |
| currencies.list | только документированные 429, 500 |
| rates.get | 404 `/api/problems/asset_not_found`, `/api/problems/currency_not_found` |
| invoices.list | 401 unauthorized; 429; 500 |
| invoices.retrieve | 400 `/api/problems/missing_invoice_identifier`; 401; 404 `/api/problems/invoice_not_found`; 429; 500 |
| будущий invoice payments list | дополнительно 400 `/api/problems/validation_error`, описание Invalid cursor |

Общие типы: 429 `/api/problems/rate_limit_exceeded`, 500 `/api/problems/internal_error`. Список документированных codes не исключает gateway 502/503, не-JSON ответ или новый problem type. В текущем срезе fallback API error сохраняет HTTP status, problem object (если JSON — объект), x-request-id и retry-after при наличии. Произвольное тело и остальные headers пока не сохраняются; отдельный raw response API отложен. Transport/timeout сохраняют исходное исключение в `__context__`, но подавляют его автоматическую печать, чтобы исходное сообщение HTTP-клиента не утекало в логи.

В OAS нет численных request/sec лимитов, гарантированного `Retry-After`, request-id header или схемы exponential backoff. Первый transport не повторяет операции автоматически. Будущая retry policy должна быть bounded, учитывать Retry-After при его наличии и различать read-only request и финансовую mutation. Для POST нельзя выводить безопасность повторения только из имени поля client ID.

### Клиентские ID и предотвращение дублей

| Операция | Поле | OAS required | Ограничение |
| --- | --- | --- | --- |
| invoice create | clientInvoiceId | нет | maxLength в create schema не указан; retrieve query maxLength 100 |
| cheque create | clientChequeId | нет | maxLength 50 |
| payout create | clientPayoutId | нет | maxLength 50 |
| withdrawal create | clientWithdrawalId | **да** | maxLength 150; retrieve query maxLength 100 |
| mass-payout item | clientPayoutId | нет | maxLength 50 |

В create descriptions cheque/payout/withdrawal IDs предназначены для предотвращения double spends. Из OAS нельзя установить срок хранения дедупликации, scope уникальности и означает ли повтор с тем же ID replay старого результата или ошибку. Документированы ошибки `client_id_already_taken`, `payout_client_id_duplicate`; для invoice это прежде всего client correlation ID. SDK не генерирует новый ID при retry и не скрывает duplicate response.

Mass payouts возвращают `successPayouts` и `errorPayouts` внутри HTTP 200. Не считать весь batch успешным по HTTP status, не повторять весь batch при наличии частичных ошибок. Сначала необходим разбор по каждому item и подтверждённая семантика client ID.

## 8. Webhooks Current

Webhook signing secret отличается от JWT API token. Current app получает его в настройках Webhook Token. Старый Legacy secret после перехода на Current недействителен.

Headers:

- `Signature-Timestamp`: Unix timestamp **в миллисекундах**;
- `Signature-Version`: текущее значение `v1`;
- `Signature`: hex HMAC-SHA256.

Подписывается последовательность `Signature-Timestamp + "." + raw request body`. Ключ — webhook secret без дополнительного SHA256 преобразования. Проверку выполняем до JSON parsing на исходном body; повторная JSON serialization меняет подписанные байты. Сравнение подписи должно быть constant-time. Timestamp header — отдельное значение, не `timestamp` из JSON body.

Проверка допустимой давности delivery — полезная SDK policy с явно настраиваемой tolerance и тестовыми часами; конкретное допустимое окно/расписание retries источник не гарантирует. Нельзя выдать произвольные пять минут за правило API.

Все основные webhook envelope DTO имеют обязательные `id`, `timestamp`, `type`, `data`. `id` delivery предназначен для dedupe и стабилен при повторной доставке. Dedupe storage остаётся ответственностью приложения; stateless подпись не предотвращает повторную обработку валидного webhook.

Invoice `data` различается по `event`:

- `invoice_status_changed`: `event`, `invoice`; payment отсутствует;
- `payment_status_changed`: `event`, `invoice`, `payment`.

Когда платёж завершает invoice, могут отправляться оба события. Порядок доставки **не гарантируется**, retry может сдвинуть событие в очереди. Каждое событие обрабатывается самостоятельно, dedupe — по верхнему `id`. Для учёта успешного платежа: точные `event == "payment_status_changed"` и `payment.status == "paid"`; для завершения invoice: точные `event == "invoice_status_changed"` и `invoice.status == "paid"`. Unknown event игнорируется безопасно с доступом к raw payload, а не считается ошибкой подписи.

Payment finality определяется `payment.finalizedAt != null`. `InvoicePaymentDto.id` описан как уникальный идентификатор для сопоставления webhook и REST payments, но не включён в required — см. known issues.

Источники: `#/info/description`, `#/components/schemas/InvoiceWebhookDto`, `#/components/schemas/InvoiceStatusChangedWebhookDataDto`, `#/components/schemas/PaymentStatusChangedWebhookDataDto`, `#/components/schemas/ChequeWebhookDto`, `#/components/schemas/PayoutWebhookDto`, `#/components/schemas/WithdrawalWebhookDto`.

Webhook реализация — следующий этап после read-only среза; signing fixtures можно подготовить без серверного вызова и средств.

## 9. Known schema defects и неоднозначности

Исходные JSON сохраняются неизменными. Ниже отделены факты схемы от интерпретации SDK.

| ID | JSON pointer | Наблюдение | Решение / проверка |
| --- | --- | --- | --- |
| PAY-001 | `#/servers` | Current servers пуст | Base URL берём из официального REST reference, держим явную настройку окружения |
| PAY-002 | `#/paths/~1api~1v1~1rates/get/summary`, `#/paths/~1api~1v1~1rates/get/security` | Summary optional auth; bearer security без `{}` требует auth | Проверить no-token smoke; не генерировать обязательность только из security |
| PAY-003 | `#/components/schemas/InvoiceDto/properties/expiresAt` | object + date-time, string example; prose допускает null, nullable отсутствует | Модель datetime или null; сохранить fixture после живого подтверждения |
| PAY-004 | `#/components/schemas/InvoicePaymentDto/properties/finalizedAt` | object + date-time, nullable true, string example | Интерпретировать как datetime или null |
| PAY-005 | `#/components/schemas/InvoiceInternalTransactionDto/properties/payAmount`, `payCurrency`, `receiveAmount`, `receiveCurrency`, `finalizedAt`; аналогичные поля `InvoiceBlockchainTransactionDto` | Prose допускает null; nullable отсутствует | Nullable response override; проверить pending/finalized fixtures |
| PAY-006 | `#/components/schemas/InvoicePaymentDto/properties/transactions/discriminator` | Discriminator находится на array, тогда как oneOf находится в items | Разбирать discriminator каждого item; не доверять такой генерации |
| PAY-007 | `#/components/schemas/InvoicePaymentDto/required` | id описан для сопоставления REST/webhook, но не required | Пока id optional, не делать обязательным без доказательства |
| PAY-008 | `#/components/schemas/InvoiceCreateRequestDto/required` | Required только priceCurrency; errors требуют amount и запрещают одновременно priceAmount/minPayment | В write phase выразить условие отдельной validation; сверить open-amount semantics |
| PAY-009 | `#/components/schemas/MassPayoutsCreateRequestDto/properties/payouts/items/maxLength` | maxLength 500 на object item, а не maxItems на массиве | Не считать это валидным ограничением размера batch; уточнить реальный лимит |
| PAY-010 | `#/components/schemas/MassPayoutsPayoutRequestDto/properties/targetType`, `#/components/schemas/MassPayoutsErrorResponseDto/properties/targetType` | Enum допускает 3 target types, prose только TelegramUserId | Для batch планировать telegram_user_id до уточнения |
| PAY-011 | `#/components/schemas/InvoiceDto/properties/status`, `#/components/schemas/InvoicePaymentDto/properties/status`, transaction statuses, webhook event fields | Closed enum против prose о расширении | Response decode принимает unknown strings/events |
| PAY-012 | `#/paths/~1api~1v1~1invoices/get/parameters/5/schema`, `#/components/schemas/CursorPaginationResponseDto/properties/total`, `#/components/schemas/InvoiceCreateRequestDto/properties/numPayments`, `#/components/schemas/WithdrawalQuotasResponseDto/properties/precision` | Счётчики/limit/precision представлены number | Не интерпретировать как money; integer coercion проверять fixtures |
| PAY-013 | `#/paths/~1api~1v1~1invoices/post/responses/401/content/application~1json/schema/description` | Current 401 description “Unknown API Key” | Auth определяется bearer scheme, не устаревшим текстом ошибки |
| PAY-014 | `#/paths/~1api~1v1~1invoice/delete/responses/200`, `#/paths/~1api~1v1~1cheques/delete/responses/200` | Нет response content/schema | Не требовать JSON body |
| PAY-015 | `#/paths/~1api~1v1~1invoices/get/parameters/2`, `#/paths/~1api~1v1~1rates/get/parameters/1` | Array query без explicit style/explode | OAS default repeated keys, подтвердить живым запросом |
| PAY-016 | `#/components/schemas/WithdrawalCreateRequestDto/properties/clientWithdrawalId/maxLength`, `#/paths/~1api~1v1~1withdrawal/get/parameters/1/schema/maxLength` | Create допускает 150 chars, retrieve только 100 | Не обещать retrieve by client ID для всей create длины; уточнить upstream |
| PAY-017 | `#/paths/~1api~1v1~1withdrawal/get/parameters`, `#/paths/~1api~1v1~1withdrawal/get/responses` | Оба идентификатора optional; нет документированного missing-identifier 400 | Уточнить семантику до write/retrieve withdrawal реализации |

В PAY-005 перечисленные короткие имена после первого pointer обозначают поля того же `properties`; полный exact pointer для примера: `#/components/schemas/InvoiceBlockchainTransactionDto/properties/receiveAmount`.

Дополнительная семантическая разница: Current `callback.callbackUrl` — webhook endpoint; Legacy invoice `callbackUrl` — payer return link. Нельзя переносить имя и смысл без migration mapping.

## 10. Legacy → Current

| Аспект | Legacy | Current |
| --- | --- | --- |
| Auth | Rocket-Pay-Key | Authorization Bearer JWT |
| Mainnet snapshot server | https://pay.xrocket.exchange/ | servers пуст; официальный Current base URL выше |
| Маршруты invoice | /tg-invoices, /tg-invoices/{id} | /api/v1/invoices, /api/v1/invoice |
| Cheques | /multi-cheque | /api/v1/cheques, /api/v1/cheque |
| User transfer | POST /app/transfer | POST /api/v1/payouts |
| App deposit | POST /app/deposit | Однозначный replacement в Current OAS отсутствует |
| Withdrawal | /app/withdrawal, /app/withdrawal/status/{withdrawalId}, /app/withdrawal/fees | /api/v1/withdrawals, /api/v1/withdrawal, /api/v1/withdrawal-quotas |
| Available currencies | /currencies/available | /api/v1/currencies |
| Withdrawal link | GET /withdrawal-link | POST /api/v1/withdrawal-link |
| Health/version | /version, /health | /health; /version отсутствует |
| Success shape | преимущественно success/data wrapper | direct DTO / массив |
| Pagination | data.results + total/limit/offset | items + pagination.total/next; payments без total |
| Invoice ID в response | number | string |
| Money | JSON numbers во многих DTO | decimal strings |
| Invoice lifetime | expiredIn, seconds; default 0 | expiresIn, milliseconds; create default 3600000 |
| Invoice status | active, paid, expired | + partially_paid, cancelled |
| Invoice links | link | links.telegramBotLink/telegramMiniAppLink/webLink |
| App information | name, feePercents, balances вместе | app-info отдельно, balances отдельно |
| Errors | success:false, message, optional errors | type/title/status/detail/instance/kind, optional info |
| Webhook signature | Rocket-Pay-Signature; HMAC key SHA256(app token) | Signature-*; HMAC key отдельный secret без transform |

Legacy содержит собственные дефекты: `AppBalance.currency/balance` помечены object вопреки scalar examples; string length иногда выражена numeric maximum; не следует использовать его schema для моделирования Current. Legacy поддержка в будущем требует отдельного явного adapter/namespace, не флага, незаметно меняющего auth/DTO/units внутри Current client.

## 11. Проверки первого этапа

Offline contract tests через подставной transport покрывают реальные различия wire contract:

1. Точный HTTP method/path, отсутствие двойного `/api/v1`, JWT header и отсутствие утечки токена.
2. Public currencies request без токена; optional rates отдельно после уточнения.
3. Aliases `invoice_id → invoiceId`, `client_invoice_id → clientInvoiceId`; None опущен, оба ID сохраняются с серверным приоритетом invoiceId.
4. Повторяющиеся query keys для ids/assets; base default не подменяется примером; filter/cursor не теряются.
5. Decimal без float: большие значения, много десятичных знаков, trailing zeros; empty balances.
6. Invoice с минимальными required полями, отсутствующим priceAmount, null expiresAt, timezone-aware date-time и unknown status.
7. Page с next cursor и конечная page с next null; разные page schemas для payments; additional fields не ломают decode.
8. 401/404/429/500 problem objects; unknown type/kind; JSON без обязательных problem fields; non-JSON HTTP error; transport timeout.
9. По умолчанию один HTTP attempt; injected HTTP client закрывается только владельцем, SDK-owned client закрывается SDK.

Live smoke opt-in: публичные GET currencies/rates/health, затем приватные app.info/app.balances/invoices.list/retrieve только при testnet JWT. Отсутствие testnet token означает пропуск live private tests с понятной причиной, а не подмену fixture живым успехом. POST/PUT/DELETE для первого этапа не нужны.

Стабильные fixtures записываем без токенов, персональных данных и платежных реквизитов. В отчёте проверки различаем offline contract pass и live verification; успешный mock не подтверждает дефекты upstream и optional auth.

## 12. Открытые вопросы до расширения SDK

- Принимает ли rates no-token запрос стабильно во всех окружениях и отличается ли его поведение при auth?
- Поддерживают ли ids/assets OAS default repeated keys? Есть ли max count и допускается ли comma-separated форма?
- Какие именно nullable поля реально возвращаются как null, а какие опускаются? Подтвердить pending и finalized invoice payments.
- Возвращаются ли total/limit/precision только integers, и какие default/minimum limit действуют в каждом list endpoint?
- Что происходит при одинаковом client ID и одинаковом/разном body: duplicate error или replay, каков срок и scope дедупликации?
- Почему длина clientWithdrawalId различается между create и retrieve?
- Каков фактический batch limit mass payouts, какие target types разрешены и как атомарность/частичный успех соотносятся с balance checks?
- Каковы реальные rate limits и response headers, есть ли Retry-After и request correlation id?
- Каковы webhook retry schedule, delivery retention, допустимый clock skew и политика rotation секрета?
- Есть ли гарантированный machine-readable stable error code помимо type URI и устойчивы ли kind значения?
- Нужен ли Legacy продуктово, или достаточно Current SDK и migration guide?

Эти вопросы не блокируют offline read-only каркас. Они должны быть закрыты подтверждёнными fixtures/официальным уточнением перед заявлением соответствующих гарантий SDK.
