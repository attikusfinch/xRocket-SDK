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

## 4. Поддерживаемые методы SDK

Read-only методы проверяют общий transport, auth, сериализацию параметров, ошибки
и модели. Invoice create/delete добавлены P009, payment address — P010,
cheque create/update/delete — P011
поверх request foundation P008;
их реализация и проверка offline не означают запуск реальных мутаций.

### `health.get()`

`GET /health` без обязательного JWT, через общий transport обоих клиентов.
Путь находится вне `/api/v1`; разрешён ровно `/health`, без query/fragment или
произвольных корневых маршрутов. Настройки HTTP pooling/ownership и auth isolation
совпадают с остальными публичными методами.

Ответ `Health` содержит обязательный `status: str`. `info`, `error`, `details`
могут отсутствовать (PAY-018): тогда Python-поле равно None, состояние компонентов
неизвестно. Если поле присутствует — это список `HealthComponent` с обязательными `name: str`,
`status: str` и необязательным `message`. Статусы остаются строками, неизвестные
поля сохраняются на обоих уровнях. Не-2xx проходит общую классификацию HTTP ошибок;
некорректный success response вызывает `ResponseValidationError`.

Источник: `#/paths/~1health/get/responses/200/content/application~1json/schema`
(inline schema), с явным omission override PAY-018.

P007 live testnet 2026-10-17 обнаружила PAY-018: HTTP 200 содержит только
`{"status":"ok"}`. P019 сохраняет missing collections как None вместо
придуманных пустых массивов. `[]` означает явно сообщённое отсутствие элементов;
отсутствующая error collection сама по себе не подтверждает отсутствие ошибок
компонентов. Явный null отвергается: OAS не nullable, live подтвердил omission.
Полный OAS response по-прежнему типизирован, неизвестные поля/statuses сохраняются.
Для lossless roundtrip missing полей нужен `model_dump(exclude_unset=True)`:
обычный dump включает default None, которые не являются допустимыми wire arrays.
Python Optional/генерируемая JSON Schema не заменяют этот runtime контракт.

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

### `invoices.create(request=InvoiceCreateRequest(...))`

`POST /api/v1/invoices`, обязательный JWT, JSON body из отдельного RequestModel.
Только HTTP 200 декодируется в прежний Invoice; 201 не переносится с payment address.
Resource принимает только InvoiceCreateRequest, raw dict/response/другой DTO не отправляет.
Четыре request класса экспортируются из xrocket.pay и xrocket.pay.models;
response InvoiceCallback/InvoiceURL/InvoiceCustomer не используются как вход.

| Python поле | Wire alias | Контракт / локальная validation |
|---|---|---|
| price_currency | priceCurrency | required str, без выдуманного currency enum/minLength |
| price_amount / min_payment | priceAmount / minPayment | optional RequestMoney (Decimal/string), только одна сумма одновременно; numeric bounds не заданы |
| num_payments | numPayments | strict int 1–1000000; integer-only — SDK policy при OAS number (PAY-012) |
| expires_in | expiresIn | strict int миллисекунд, 0 сохраняется; диапазон не задан, OAS default 3600000 не подставляется |
| payout_currency / pay_currencies | payoutCurrency / payCurrencies | optional str / list[str], пустые значения не теряются |
| client_invoice_id | clientInvoiceId | optional str, create maxLength отсутствует; GET/DELETE100 не переносится |
| description | description | optional str maxLength1000 |
| callback / url / customer | callback / url / customer | отдельные nested request DTO, все поля optional; {} допустим |
| data | data | optional object с произвольными JSON keys/values |
| platform_id | platformId | optional str без UUID format |

InvoiceCallbackRequest: callback_url (max500) и object payload. InvoiceURLRequest:
success_url/cancel_url (max500). InvoiceCustomerRequest: id/email/telegram_id/
telegram_username — strings без выдуманных format/length constraints.
Request aliases camelCase, неизвестные поля запрещены; типы strict.
Все optional поля пропускаются по умолчанию, explicit None запрещён (OAS не nullable).
Явные {}, [], пустые строки и 0 не заменяются missing; None внутри custom JSON
payload разрешён как JSON null. Core serializer сохраняет required wire fields
даже у model_construct с вручную пустым fields_set, не меняя исходный DTO.

PAY-008 остаётся открытым: schema required содержит только priceCurrency,
minPayment описан для open amount, error schema перечисляет missing_invoice_amount.
SDK допускает отсутствие обеих сумм по schema и запрещает одновременное наличие
по документированному amount_conflict, включая нулевые значения. Server acceptance
варианта без сумм и фактические monetary bounds не подтверждены; ошибки сервера
проходят общий APIError без retry. Также не навязываются положительный expiresIn,
URL/email/UUID/username formats или фиксированная денежная precision.
Prose limit4KB для data/callback.payload сохраняется как серверное ограничение:
метрика size/JSON encoding/byte-vs-char не задана, локальный числовой предел не угадан.

### `invoices.delete(invoice_id=None, client_invoice_id=None)`

`DELETE /api/v1/invoice`, обязательный JWT, без JSON request body. Нужен хотя бы
один непустой str ID 1–100; оба передаются буквально при наличии, по описанию API
сервер использует invoiceId. Общий identifier helper усилен type check без изменения
корректных GET inputs. Response policy — строго пустой HTTP 200 → None (PAY-014).
JSON/whitespace body или иной 2xx отвергается как ResponseValidationError.
400/401/404/429/500 проходят общий HTTP error decoder, попытка только одна.

Источники обоих write methods: точные POST/DELETE, InvoiceCreateRequestDto,
InvoiceCallbackRequestDto, InvoiceUrlRequestDto, InvoiceCustomerRequestDto.
Все подтверждения P009 offline; live create/delete не запускались.

### `invoices.create_payment_address(request=..., invoice_id=None, client_invoice_id=None)`

`POST /api/v1/invoices/payments/address`, обязательный JWT. Публичное имя одинаково
у sync/async invoice resource; все аргументы keyword-only. Отдельный
`InvoiceCreatePaymentAddressRequest` содержит только обязательный `pay_network`:
request enum `TON`, `BSC`, `ETH`, `BTC`, `TRX`, `SOL`. Wire alias — `payNetwork`,
типы strict, extra fields и explicit None запрещены. Resource принимает только
этот DTO; raw dict/response/InvoiceCreateRequest автоматически не преобразует.
Оба новых класса экспортированы из `xrocket.pay` и `xrocket.pay.models`.

Query `invoiceId` / `clientInvoiceId` используют прежний invoice identifier helper:
хотя бы один непустой str длиной 1–100; значения сохраняются буквально, оба при
наличии передаются в query. По OAS сервер выбирает invoiceId при двух ID.
Идентификаторы не попадают в JSON body; payNetwork не попадает в query.

Только HTTP **201** с JSON декодируется в `InvoicePaymentAddress`:

| Python поле | Wire alias | Контракт |
|---|---|---|
| address | address | required str |
| pay_currency | payCurrency | required str |
| pay_network | payNetwork | required open str, неизвестная сеть сохраняется |
| expires_at | expiresAt | required aware datetime, OAS string/date-time |
| min_amount | minAmount | optional Money → Decimal, без округления |

У этого expiresAt корректный OAS string/date-time, nullable отсутствует.
PAY-003 относится только к InvoiceDto.expiresAt и сюда не переносится:
missing/null/naive date-time отвергаются. MinAmount при omission равен None,
при наличии обязан быть суммой; explicit null отвергается по non-nullable OAS.
Для roundtrip с omission используйте `model_dump(exclude_unset=True)`.
Unknown response fields сохраняются. Иной 2xx, пустой/malformed JSON или
повреждённый response дают ResponseValidationError. HTTP 400/401/403/404/429/500
и прочие non-2xx проходят общий HTTP problem decoder с metadata.
Метод делает одну попытку без retries/redirects, не выполняет оплату на адрес.

Источники: `#/paths/~1api~1v1~1invoices~1payments~1address/post`,
`#/components/schemas/InvoiceCreatePaymentAddressRequestDto`,
`#/components/schemas/InvoicePaymentAddressResponseDto`.
Подтверждения только offline MockTransport; live address creation не запускался.

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

### `invoices.payments(invoice_id=None, client_invoice_id=None, cursor=None, limit=None)`

`GET /api/v1/invoice/payments` с обязательным JWT. Нужен хотя бы один непустой
invoice identifier длиной до 100; SDK передаёт оба, если заданы оба, а сервер
использует `invoiceId`. Cursor передаётся буквально, включая пустую строку;
`limit` проверяется как целое 1–1000, bool не допускается, как у invoices.list.

Ответ `InvoicePaymentPage` содержит `items: list[InvoicePayment]` и отдельную
`InvoicePaymentPagination` с обязательным nullable `next`, без поля total.
Каждый вызов делает один запрос. Конец страницы определяется только `next is None`,
а не длиной items. Дополнительные поля page/pagination также сохраняются.

У платежа обязательны status, pay/receive amounts и currencies, transactions;
`id` необязателен (PAY-007), `finalized_at` — aware datetime или None (PAY-004).
Завершение определяется `finalized_at is not None`; неизвестный status не означает
paid или finalized. Денежные суммы разбираются через Money без float.

Discriminator `type` применяется к каждому item transactions (PAY-006):
`internal` → `InvoiceInternalTransaction`, `blockchain` →
`InvoiceBlockchainTransaction`. Их nullable money/currency/finalized_at учитывают
PAY-005; payer и blockchain tx details типизированы. Неизвестная строка type
возвращает `UnknownInvoiceTransaction`, сохраняя поля без интерпретации. Отсутствующий
или нестроковый type и некорректные поля известного типа вызывают
`ResponseValidationError`, без fallback для повреждённого известного объекта.
Неизвестные response statuses и поля сохраняются (PAY-011).

Источники: `#/paths/~1api~1v1~1invoice~1payments/get`,
`InvoicePaymentListResponseDto`, `InvoicePaymentListPaginationDto`,
`InvoicePaymentDto`, `InvoiceInternalTransactionDto`,
`InvoiceBlockchainTransactionDto` и их nested DTO. Проверено offline;
nullable overrides пока не подтверждены реальными payment records.

### `cheques.create(request=ChequeCreateRequest(...))`

`POST /api/v1/cheques`, обязательный JWT, exact HTTP 200 с `Cheque`.
Request DTO отдельны от response: strict типы, camelCase aliases, extra forbid.
Публичны `ChequeCreateRequest`, `ChequeCallbackRequest`, `ChequeURLRequest` и
`ChequeUpdateRequest` из `xrocket.pay` и `xrocket.pay.models`.

| Python поле | Wire alias | Контракт create |
|---|---|---|
| asset | asset | required str |
| amount | amount | required finite Decimal/decimal string → JSON string |
| client_cheque_id | clientChequeId | optional str, maxLength 50 |
| password | password | optional SecretStr/string input, maxLength 100 |
| description | description | optional str, maxLength 1000 |
| target_type | targetType | optional enum user_id / telegram_user_id / telegram_username |
| target | target | optional str, maxLength 100; передаётся вместе с target_type |
| callback | callback | отдельный request DTO; callback_url max500, payload object |
| url | url | отдельный request DTO; success_url / cancel_url max500 |

Все optional свойства можно опустить; explicit None запрещён по non-nullable
schema. Пустые строки/объекты допустимы, minLength/bounds суммы не угаданы.
Payload 4KB описан prose без size metric; локальный лимит не вводится.
Password скрыт в repr и обычных model dumps; cheque validation удаляет input
из ошибок валидации полей и model policies, включая structured errors/json.
Request serializer явно раскрывает SecretStr только через password field serializer
в outbound JSON bytes. Эти байты и произвольный raw server problem являются
явно доступными данными: вызывающий код не должен журналировать их с секретами.
SDK body не журналирует; сообщения HTTP/timeout/response ошибок остаются общими.
При подготовке request строки и ключи проверяются на surrogate code points
U+D800–U+DFFF. Они отвергаются generic ValueError до создания JSON text и I/O,
включая password и callback payload. Это SDK Unicode/encoding policy: исключение
не содержит JSON/password в args/object/cause/context. Нормальный Unicode,
включая emoji/astral symbols, сохраняет точный UTF-8 wire format.

### `cheques.update(request=ChequeUpdateRequest(...), cheque_id=None, client_cheque_id=None)`

`PUT /api/v1/cheques`, обязательный JWT, exact HTTP 200 с `Cheque`.
Body содержит только optional description str max1000. Unset → `{}` (schema
допускает), `description=""` явно очищает описание, `None` отвергается.
Amount, asset, password, IDs, response extras и остальные create поля запрещены.
Resource принимает именно update DTO, без автоматического переноса response.

### `cheques.delete(cheque_id=None, client_cheque_id=None)`

`DELETE /api/v1/cheques`, обязательный JWT, без request body. Только пустой
HTTP 200 возвращает None; whitespace/JSON null/JSON object отвергаются (PAY-014).
Update/delete identifiers передаются в query: хотя бы один непустой str 1–100
(minimum — прежний SDK guard). Оба передаются буквально, приоритет не обещается.
Create client ID max50 не переносится на query max100.
Неожиданные 2xx/повреждённые JSON или Cheque вызывают ResponseValidationError;
non-2xx использует общий problem decoder. Одна попытка, без retries/ID generation.

Источники: `#/paths/~1api~1v1~1cheques/post`, `.../put`, `.../delete`,
`ChequeCreateRequestDto`, `ChequeUpdateRequestDto`, `ChequeCallbackRequestDto`,
`ChequeUrlRequestDto`, `ChequeResponseDto`. Подтверждение только offline;
live cheque mutations не выполнялись.

### `cheques.list(...)`

`GET /api/v1/cheques` с обязательным JWT возвращает одну `CursorPage[Cheque]`.
`from_date` / `to_date` — optional timezone-aware `datetime`, сериализуемые
`isoformat()` в `fromDate` / `toDate` с сохранением offset и долей секунды.
Naive datetime и строки не принимаются; это явная политика входного Python API.
OAS задаёт ISO 8601 date-time, но не требует обеих дат и не ограничивает их порядок.

`target_type` / `target` передаются вместе как `targetType` / `target`.
Request target type: `user_id`, `telegram_user_id`, `telegram_username`;
target — строка до 100 символов (minLength в OAS отсутствует).
Request state: `active`, `completed`, `draft`, `error`.
Cursor передаётся буквально, включая пустую строку. `limit` — целое 1–1000,
bool отвергается; integer-only — политика SDK при OAS type number с теми же
minimum/maximum. `None` опускается; defaults серверу не навязываются.
Конец страницы определяется `pagination.next is None`, даже при пустых items.
По описанию API list исключает отменённые чеки; SDK дополнительных фильтров
результата не вводит.

### `cheques.retrieve(cheque_id=None, client_cheque_id=None)`

`GET /api/v1/cheque`, точный singular path. Нужен хотя бы один непустой строковый
identifier длиной до 100; ведущие нули и произвольные символы сохраняются.
Переданные оба ID уходят как `chequeId` / `clientChequeId`; OAS не задаёт их
приоритет. Ограничение 50 из create здесь не применяется. Требование хотя бы
одного следует из документированного 400 `missing_cheque_identifier`.

`ChequeResponseDto` требует только `chequeId`, `asset`, `links`, `deleted`.
`Cheque.state` остаётся optional str, неизвестные состояния сохраняются.
`amount` в schema отсутствует: SDK его не требует и не придумывает денежный
контракт; дополнительные поля, включая сумму при её появлении, сохраняются raw.
Все поля `ChequeLinks`, `ChequeCallback`, `ChequeURL` необязательны; `links: {}`
валиден, callback payload типизирован как object. Optional response поля допускают
None по существующей политике Pay-моделей; upstream nullability этим не подтверждена.
Retrieve может вернуть отменённый чек с `deleted=true`.

Источники обоих методов: `#/paths/~1api~1v1~1cheques/get`,
`#/paths/~1api~1v1~1cheque/get`, `ChequeResponseDto`, `ChequeListResponseDto`,
`ChequeLinkResponseDto`, `ChequeCallbackResponseDto`, `ChequeUrlResponseDto`.
Контракт проверяется offline; живые cheque records пока не проверялись.

### `payouts.create(request=PayoutCreateRequest(...))`

`POST /api/v1/payouts`, обязательный JWT, exact HTTP 200 с существующим `Payout`
(`AppPayoutResponseDto`). Sync/async сигнатуры совпадают. Request DTO отделены
от response, используют strict типы, camelCase aliases и extra forbid.
`PayoutCreateRequest` и `PayoutCallbackRequest` публичны из `xrocket.pay`
и `xrocket.pay.models`.

| Python поле | Wire alias | Контракт create |
|---|---|---|
| target | target | required str, maxLength 100 |
| target_type | targetType | required enum user_id / telegram_user_id / telegram_username |
| asset | asset | required str, без enum/maxLength |
| amount | amount | required finite Decimal/decimal string → точная JSON string |
| client_payout_id | clientPayoutId | optional str, maxLength 50 |
| description | description | optional str, maxLength в schema нет |
| callback | callback | отдельный request DTO; callback_url max500, payload object |

Все optional свойства, включая callback_url/payload внутри callback, можно
опустить; explicit None запрещён по non-nullable OAS. `callback={}` и пустые
строки/объекты сохраняются. MinLength, положительность/диапазон суммы и URL
format schema не задаёт; SDK их не угадывает. Payload max4KB задан prose без
size metric, локальное ограничение не вводится. Общий serializer повторно
валидирует DTO до I/O, в том числе constructed/mutated значения; response DTO
не сериализуются как request. Response status/target_type остаются открытыми
строками, неизвестные поля сохраняются.

Client ID принадлежит вызывающему коду: SDK его не генерирует, не заменяет и
не добавляет при omission. HTTP 400 `/api/problems/payout_client_id_duplicate`
проходит как обычный `APIError` с исходными problem/metadata. Скрытого retry
или GET lookup нет. `RequestTimeoutError` оставляет неизвестный итог операции:
после единственной HTTP попытки сервер мог создать payout. Сохраните стабильный
client ID до отправки, затем при необходимости отдельно вызовите
`payouts.retrieve(client_payout_id=saved_id)` (async — с `await`). Даже not-found
не доказывает, что повтор безопасен: retention/scope/replay semantics не
подтверждены. Без переданного client ID lookup по нему недоступен.

Источники: `#/paths/~1api~1v1~1payouts/post`, `AppPayoutCreateRequestDto`,
`PayoutCallbackRequestDto`, `AppPayoutResponseDto`. Проверено offline,
live выплаты не выполнялись.

### `payouts.create_mass(request=MassPayoutCreateRequest(...))`

`POST /api/v1/mass-payouts`, обязательный JWT, exact HTTP 200 возвращает
`MassPayoutResult`. Sync/async сигнатуры совпадают. Все новые DTO публичны из
`xrocket.pay` и `xrocket.pay.models`; request отделён от response.

`MassPayoutCreateRequest` требует `asset: str` и `payouts: list[MassPayoutItemRequest]`.
Asset задаётся один раз, в item его нет. Item требует `target: str` (max100),
`target_type` и `amount` (finite Decimal/decimal string → точная JSON string).
Optional: `client_payout_id` (max50), `description` (без schema maxLength),
`callback: PayoutCallbackRequest` (callback_url max500 и object payload).
Strict inputs/extra forbid, aliases, recursive omission, запрет explicit None,
повторная валидация constructed/mutated DTO и точные деньги следуют single payout.
SDK не вводит minLength, positivity/amount bounds или payload4KB size metric.

PAY-010: request принимает только `telegram_user_id`, следуя operation summary
«Telegram users only» и targetType prose «only TelegramUserId». Enum одновременно
перечисляет user_id / telegram_user_id / telegram_username. Это явная ограниченная
SDK policy до уточнения upstream, а не утверждение о live поведении сервера.
Single payout сохраняет три target types. Response target_type остаётся открытым str.

PAY-009: массив payouts не имеет minItems/maxItems. `items/maxLength: 500` стоит
на object item и не задаёт длину массива. SDK не угадывает ни предел500, ни
обязательную непустоту и не разбивает batch автоматически. Серверный предел и
принятие пустого/большого массива остаются неподтверждёнными; offline cases
проверяют только отсутствие выдуманных локальных ограничений и второй HTTP попытки.

Оба response массива обязательны даже при пустом содержимом:

- `success_payouts` / successPayouts — `list[Payout]` из AppPayoutResponseDto;
  сохраняются payout_id, client_payout_id, точный amount и открытые status/target_type.
- `error_payouts` / errorPayouts — `list[MassPayoutError]`: required target,
  target_type, Money amount, reason; optional client_payout_id и description.
  В schema ошибки нет asset, payoutId, callback или request index.
- `MassPayoutErrorReason` требует type/title/status/detail/instance/kind. Status
  по OAS number сохраняется как strict finite int/float без integer coercion;
  type/kind открыты. Неизвестные поля сохраняются на wrapper/item/reason.

`has_errors` означает непустой error_payouts; `is_partial` — непустые оба массива.
All-error HTTP200 остаётся typed результатом с has_errors=True/is_partial=False.
HTTP200 не означает, что все items успешны; при отсутствующем/невалидном массиве
вызывается общий ResponseValidationError, а не создаётся ложный пустой результат.
Отдельные non-2xx сохраняют общие APIError/problem/metadata правила.

Каждый response список сохраняет исходные строки IDs, ведущие нули, дубликаты
и порядок сервера; dict-дедупликации и positional matching с request нет.
OAS не гарантирует общий порядок/полноту correlation и не предоставляет index
ошибки. Сохраните уникальный caller-owned client ID каждого item до отправки;
при отсутствующем/повторённом ID однозначная корреляция не обещается. SDK не
генерирует/меняет ID и не подставляет его в response из исходного request.

Один вызов — один HTTP attempt, без splitting, fan-out single payouts, lookup,
replay или retry. Успешные items автоматически не повторяются. Timeout оставляет
исход отдельных items неизвестным; возможная явная сверка через retrieve по
сохранённым client IDs — отдельное действие. Ни частичная ошибка, ни not-found
не доказывают безопасность повторной выплаты. Balance-check/атомарность,
deduplication scope/retention и replay semantics live не проверены.

Источники: `#/paths/~1api~1v1~1mass-payouts/post`, MassPayoutsCreateRequestDto,
MassPayoutsPayoutRequestDto, MassPayoutsCreateResponseDto, MassPayoutsErrorResponseDto,
MassPayoutsReasonResponseDto, AppPayoutResponseDto и PayoutCallbackRequestDto.
Snapshots не менялись; live batch/реальные выплаты не выполнялись.

### `payouts.list(from_date=None, to_date=None, cursor=None, limit=None)`

`GET /api/v1/payouts` с обязательным JWT возвращает одну `CursorPage[Payout]`.
Даты — optional aware datetime, передаваемые в `fromDate` / `toDate` через
`isoformat()` с сохранением offset и дробных секунд; строки и naive datetime
не принимаются по политике Python API. Можно передать каждую дату отдельно,
OAS не задаёт требование порядка дат. Cursor непрозрачен, включая пустую строку.
`None` опускается, серверные defaults не подставляются.

У `limit` в этом GET только OAS type number и example 100: **нет minimum,
maximum или default**. SDK принимает int без bool и без границ, не переносит
1–1000 из cheques/invoices. Integer-only — локальная политика Python API;
передача 0, отрицательных значений или >1000 не означает их принятие сервером.
Страница возвращается без скрытого перехода по next, в том числе при пустых items.

### `payouts.retrieve(payout_id=None, client_payout_id=None)`

`GET /api/v1/payout`, точный singular path. Хотя оба query optional, 400
`missing_payout_identifier` требует хотя бы один identifier. SDK принимает
непустые строки длиной 1–100, сохраняет ведущие нули и произвольные символы,
передаёт оба как `payoutId` / `clientPayoutId` при наличии. Приоритет OAS не задаёт;
maxLength 50 из create здесь не применяется.

У `Payout` обязательны `payout_id`, `target`, `target_type`, `asset`, `amount`,
`status`. Amount читается через Money в Decimal без float. Response status и
target type остаются строками с поддержкой неизвестных значений. Необязательны
`client_payout_id`, `description`, `callback`; в `PayoutCallback` необязательны
`callback_url` и object `payload`. Optional response поля допускают None по
существующей политике Pay, без заявления о подтверждённой live nullability.
Неизвестные поля payout/callback/page/pagination сохраняются.

Источники: `#/paths/~1api~1v1~1payouts/get`, `#/paths/~1api~1v1~1payout/get`,
`AppPayoutResponseDto`, `AppPayoutListResponseDto`, `PayoutCallbackDto`.
Особые ошибки: list — 400 `validation_error` (Invalid cursor), retrieve — 400
`missing_payout_identifier`, 404 `app_payout_not_found`. Все проходят общий
decoder HTTP ошибок без retries. Проверено offline, живые payout records
в этой задаче не используются.

### `withdrawals.create(request=WithdrawalCreateRequest(...))`

`POST /api/v1/withdrawals` с обязательным JWT; только HTTP **200** с JSON
возвращает существующий `Withdrawal`. Sync и async используют keyword-only
`request` и один контракт; async вызывается с `await`. Request/response DTO
разделены; `WithdrawalCreateRequest` и `WithdrawalCallbackRequest` доступны из
`xrocket.pay` и `xrocket.pay.models`.

| Python field | Wire field | Контракт request |
|---|---|---|
| client_withdrawal_id | clientWithdrawalId | required strict str, maxLength 150; caller-owned |
| network | network | required TON/BSC/ETH/BTC/TRX/SOL с точным регистром |
| address | address | required strict str, maxLength 100 |
| asset | asset | required strict str, без schema maxLength |
| amount | amount | required finite Decimal/decimal string → точная JSON string |
| comment | comment | optional strict str, maxLength 50 |
| callback | callback | optional отдельный WithdrawalCallbackRequest |

`network` остаётся обязательным несмотря на schema default TON. Callback содержит
optional `callback_url` (wire callbackUrl, strict str/max500) и `payload` (JSON
object). Prose говорит о max4KB payload, но не задаёт size metric; общий локальный
лимит байтов/символов не выдумывается. Все optional поля можно опустить,
explicit None запрещён: nullable в этих schemas нет. Extra fields запрещены.

У client ID/address/asset/comment/callback URL нет schema minLength: пустые строки
в этих полях не запрещаются локально, их принятие сервером не подтверждено.
Network ограничен enum, amount должен быть корректной decimal строкой/Decimal.
Рекомендуется сохранить стабильный непустой
client ID до отправки. SDK никогда не генерирует, не меняет и не урезает его.
Адрес, asset и comment сохраняются без trimming, изменения регистра, проверки
blockchain checksum или придуманного network-specific формата. Нет локального
positive/minimum/maximum amount или ограничения в 9 знаков: DTO не округляет и
не обрезает точный amount, monetary limits/валидность адреса остаются серверу.

**PAY-016:** create max150 отличается от retrieve 1–100. SDK не переносит общий
validator и не обещает lookup по client ID длиной 101–150 (либо пустому).
Для client-ID lookup выбирайте ID длиной 1–100; после успешного create сохраните
также `withdrawal_id` из ответа для явного retrieve. **PAY-017** остаётся открытым:
GET guard — локальная политика, missing-ID ответ и приоритет двух ID неизвестны.

После `RequestTimeoutError` исход неизвестен: withdrawal мог быть создан.
Делается ровно одна HTTP попытка без автоматического retry, lookup, quotas request
или blockchain polling. Timeout не доказывает отказ перевода. Явный retrieve
по сохранённому ID в пределах его GET bounds — отдельное действие; not-found
не доказывает безопасность replay. Срок/scope дедупликации и поведение повтора
не подтверждены. Ошибки API не подавляются, неожиданный 2xx/невалидный success
JSON даёт ResponseValidationError; обе ошибки также не запускают скрытые запросы.

Источники: `#/paths/~1api~1v1~1withdrawals/post`, `WithdrawalCreateRequestDto`,
`WithdrawalCallbackRequestDto`, `WithdrawalResponseDto`. Проверено только offline;
реальные withdrawals, принятие граничных значений и идемпотентность не подтверждены.

### `withdrawals.list(from_date=None, to_date=None, status=None, cursor=None, limit=None)`

`GET /api/v1/withdrawals` с обязательным JWT возвращает одну `CursorPage[Withdrawal]`.
Date filters — aware datetime → `fromDate` / `toDate` через `isoformat()`;
каждая дата optional, порядок не ограничен. Это та же политика Python API, что
у payouts: строки/naive datetime отвергаются, offset/доли секунды сохраняются.
Request status принимает только `CREATED`, `COMPLETED`, `FAIL` с точным регистром.
Cursor opaque, включая пустую строку. Limit — int без bool и без диапазона:
этот GET OAS задаёт number без minimum/maximum/default; серверные bounds неизвестны.
None queries опускаются, следующий cursor автоматически не запрашивается.

### `withdrawals.retrieve(withdrawal_id=None, client_withdrawal_id=None)`

`GET /api/v1/withdrawal`, singular path. **Локальная политика SDK** требует хотя
бы один непустой строковый ID длиной 1–100; оба передаются при наличии без
обещания приоритета. Это guard от запроса без идентификатора, не подтверждение
серверной семантики: оба query optional, missing-ID 400 в OAS отсутствует (PAY-017).
Create clientWithdrawalId имеет maxLength 150, retrieve — 100 (PAY-016).
SDK не скрывает разницу общим validator и не обещает lookup для всей create длины.

`Withdrawal` требует только withdrawal_id, network, address, asset и Money amount.
Status/comment/tx_hash/tx_link/callback optional; response network/status принимают
неизвестные строки без смены регистра. В callback оба поля optional, payload —
object. ClientWithdrawalId не описан в response DTO; при наличии сохраняется extra.
Optional response поля допускают None по существующему pattern Pay, без live
подтверждения nullability. Amount не округляется и не обрезается в SDK; upstream
описание про 9 знаков после запятой не является правилом read decoder.

### `withdrawals.quotas(network=..., asset=...)`

`GET /api/v1/withdrawal-quotas` с обязательными keyword-only network и asset.
Network — request enum `TON`, `BSC`, `ETH`, `BTC`, `TRX`, `SOL`; asset — строка.
Пустую строку asset схема не запрещает, SDK не добавляет minLength; её принятие
сервером не подтверждено. Ответ `WithdrawalQuotas` требует withdraw_min_size,
withdraw_fee (Money → Decimal), withdraw_fee_asset (str), precision.
Precision — strict конечное int | float, не деньги: OAS number (PAY-012) не
ужесточается до integer и не округляется. Bool/строки/NaN/Infinity отвергаются.
Неизвестные поля сохраняются на всех уровнях response.

Источники: три точных GET, `WithdrawalResponseDto`, `WithdrawalListResponseDto`,
`WithdrawalCallbackDto`, `WithdrawalQuotasResponseDto`. Проверено offline;
missing-ID поведение, live quotas и реальные withdrawals этим не подтверждены.

## 5. Деньги, время, идентификаторы и эволюция schema

### Деньги

Current передаёт суммы, balances, rates и fees строками. Публичные Python-модели используют `Decimal`; для будущих write methods допускаем `Decimal` и корректную decimal string, сериализуем в JSON string. Не используем binary float как промежуточный формат, не округляем без явного правила API и не считаем все активы имеющими одинаковую precision.

P008: внутренний `RequestMoney` принимает только конечный Decimal или decimal
string; float, bool, int, NaN/Infinity отвергаются до сети. Response Money остаётся
прежним типом со своей политикой чтения. Request DTO наследуют
`xrocket._core.serialization.RequestModel`; response модели в него автоматически не преобразуются.
Сериализация повторно валидирует изменённые instances и сохраняет Decimal строкой.
Это относится и к RequestModel внутри Any/payload containers. Общий serializer
принимает явный JSON/request graph, не использует неявные dataclass/bytes/date
converters и отвергает циклы, sets, non-string keys и non-finite JSON values.

Примеры wire money: `AppBalanceResponseDto.balance/available/holds`, `InvoiceDto.priceAmount/minPayment`, `InvoicePaymentDto.payAmount/receiveAmount`, `RateResponseDto.rate`, `WithdrawalQuotasResponseDto.withdrawMinSize/withdrawFee`. `WithdrawalQuotasResponseDto.precision` — отдельное числовое поле, а не сумма.

### Время и отсутствующие значения

`createdAt` и прочие `date-time` представляем timezone-aware datetime, сохраняя смысл offset. `expiresIn` Current измеряется **в миллисекундах**, включая invoice create default 3600000; `0` означает отсутствие expiration. Legacy `expiredIn` измеряется в секундах.

Отличаем missing и явный null там, где это влияет на запросы. На response стороне учитываем документированные null вопреки ошибкам OAS, перечисленным ниже. Не превращаем объектные `date-time` типы из ошибочной схемы в пользовательский dict API.

Request serializer использует wire aliases и exclude_unset: пропущенное поле
опускается, явно переданное None сериализуется как null, явный default сохраняется.
Право конкретного поля принимать null определяет endpoint DTO, не transport.
Extra response fields и response BaseModel, включая вложенные payload values,
не пересылаются автоматически; перенос в явный request dict — решение вызывающего кода.

Invoice create/delete используют общий core request с явными
success_statuses и response adapter: TypeAdapter для JSON, None для пустого body.
Ресурс invoice create выбирает 200, invoice DELETE — 200 с None;
invoice create_payment_address выбирает 201 с JSON.
Пустой JSON success, malformed JSON, неожиданный 2xx или body при empty policy
дают ResponseValidationError; non-2xx сохраняет общую HTTP problem classification.
Это offline foundation, не подтверждение живых write endpoints или идемпотентности.

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
| invoices.payments | дополнительно 400 `/api/problems/validation_error`, описание Invalid cursor |

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

После timeout одиночного payout итог неизвестен: SDK не повторяет POST и не
делает автоматическую сверку. Ручной `payouts.retrieve(client_payout_id=...)`
использует сохранённый вызывающим кодом ID. Отрицательный lookup не является
подтверждением безопасности повтора; сама дедупликация пока проверена только
на synthetic duplicate response, не на live сервере.

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
| PAY-008 | `#/components/schemas/InvoiceCreateRequestDto/required` | Required только priceCurrency; errors требуют amount и запрещают одновременно priceAmount/minPayment | P009 запрещает обе суммы, допускает ни одной по schema; acceptance open amount/без сумм и денежные bounds не подтверждены live, оставлены серверу |
| PAY-009 | `#/components/schemas/MassPayoutsCreateRequestDto/properties/payouts/items/maxLength` | maxLength 500 на object item, а не maxItems на массиве | Не считать это валидным ограничением размера batch; уточнить реальный лимит |
| PAY-010 | `#/components/schemas/MassPayoutsPayoutRequestDto/properties/targetType`, `#/components/schemas/MassPayoutsErrorResponseDto/properties/targetType` | Enum допускает 3 target types, prose только TelegramUserId | P013 batch request принимает только telegram_user_id по prose/summary; response открыт. Остальные target types/live acceptance не подтверждены |
| PAY-011 | `#/components/schemas/InvoiceDto/properties/status`, `#/components/schemas/InvoicePaymentDto/properties/status`, transaction statuses, webhook event fields | Closed enum против prose о расширении | Response decode принимает unknown strings/events |
| PAY-012 | `#/paths/~1api~1v1~1invoices/get/parameters/5/schema`, `#/components/schemas/CursorPaginationResponseDto/properties/total`, `#/components/schemas/InvoiceCreateRequestDto/properties/numPayments`, `#/components/schemas/WithdrawalQuotasResponseDto/properties/precision` | Счётчики/limit/precision представлены number | Не money. P009 numPayments/expiresIn strict integer — локальная SDK policy без silent coercion, не доказательство серверного integer-only контракта; quotas precision допускает float |
| PAY-013 | `#/paths/~1api~1v1~1invoices/post/responses/401/content/application~1json/schema/description` | Current 401 description “Unknown API Key” | Auth определяется bearer scheme, не устаревшим текстом ошибки |
| PAY-014 | `#/paths/~1api~1v1~1invoice/delete/responses/200`, `#/paths/~1api~1v1~1cheques/delete/responses/200` | Нет response content/schema | Не требовать JSON body |
| PAY-015 | `#/paths/~1api~1v1~1invoices/get/parameters/2`, `#/paths/~1api~1v1~1rates/get/parameters/1` | Array query без explicit style/explode | OAS default repeated keys, подтвердить живым запросом |
| PAY-016 | `#/components/schemas/WithdrawalCreateRequestDto/properties/clientWithdrawalId/maxLength`, `#/paths/~1api~1v1~1withdrawal/get/parameters/1/schema/maxLength` | Create допускает 150 chars, retrieve только 100 | Не обещать retrieve by client ID для всей create длины; уточнить upstream |
| PAY-017 | `#/paths/~1api~1v1~1withdrawal/get/parameters`, `#/paths/~1api~1v1~1withdrawal/get/responses` | Оба идентификатора optional; нет документированного missing-identifier 400 | В P006/P014 retrieve требует ID только как локальный SDK guard; upstream поведение без ID/приоритет двух ID не подтверждены, missing-ID 400 не утверждается. Create не зависит от этих неизвестных деталей GET |
| PAY-018 | `#/paths/~1health/get/responses/200/content/application~1json/schema` | P007 testnet 2026-10-17: HTTP 200 содержит только `{"status":"ok"}`, OAS требует также info/error/details | P019: missing collections → None (unknown), provided lists сохраняются, explicit null отвергается. Полный OAS response поддержан; [журнал](live-verification.md). Snapshot не менялся |

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

Live smoke opt-in: публичные GET currencies/rates/health, затем все реализованные
private GET только при `XROCKET_PAY_TESTNET_TOKEN`. Retrieve/payment используют
только явные ID fixtures, quotas — явную пару network/asset. Отсутствие JWT/fixtures
даёт независимые skips; сеть/HTTP/schema errors при opt-in остаются failure.
Реализация harness и результаты — в [плане](test-plan.md) и
[журнале live](live-verification.md). POST/PUT/DELETE не выполняются.

Стабильные fixtures записываем без токенов, персональных данных и платежных реквизитов. В отчёте проверки различаем offline contract pass и live verification; успешный mock не подтверждает дефекты upstream и optional auth.

## 12. Открытые вопросы до расширения SDK

- Принимает ли rates no-token запрос стабильно во всех окружениях и отличается ли его поведение при auth?
- Поддерживают ли ids/assets OAS default repeated keys? Есть ли max count и допускается ли comma-separated форма?
- Какие именно nullable поля реально возвращаются как null, а какие опускаются? Подтвердить pending и finalized invoice payments.
- Возвращаются ли total/limit/precision только integers, и какие default/minimum limit действуют в каждом list endpoint?
- Как API считает prose limit4KB для invoice data/callback.payload: bytes/characters, encoding, whitespace и scope size?
- Что происходит при одинаковом client ID и одинаковом/разном body: duplicate error или replay, каков срок и scope дедупликации?
- Почему длина clientWithdrawalId различается между create и retrieve?
- Каков фактический batch limit mass payouts, какие target types разрешены и как атомарность/частичный успех соотносятся с balance checks?
- Каковы реальные rate limits и response headers, есть ли Retry-After и request correlation id?
- Каковы webhook retry schedule, delivery retention, допустимый clock skew и политика rotation секрета?
- Есть ли гарантированный machine-readable stable error code помимо type URI и устойчивы ли kind значения?
- Нужен ли Legacy продуктово, или достаточно Current SDK и migration guide?

Эти вопросы не блокируют offline read-only каркас. Они должны быть закрыты подтверждёнными fixtures/официальным уточнением перед заявлением соответствующих гарантий SDK.
