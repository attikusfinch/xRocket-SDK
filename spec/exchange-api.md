# Exchange: проверенный контракт и первый срез

Дата исследования: **2026-10-18 (Asia/Tashkent)**. X001 — discovery/planning.
`xrocket.exchange` пока содержит только зарезервированный namespace: приведённые
ниже методы и DTO — план, не реализованный API. Pay readiness остаётся отдельным
[датированным результатом P018](pay-readiness-2026-10-18.md).

## Источники и воспроизводимость

Проверены текущие официальные [overview](https://docs.xrocket.exchange/api/exchange/exchange-api-overview)
и [REST reference](https://docs.xrocket.exchange/api/exchange/reference/exchange-rest-api).
EN reference упоминает Swagger без ссылки; ссылка найдена в
[официальной RU reference](https://docs.xrocket.exchange/ru/api/exchange/reference/http/xrocket-exchange-api).
[Swagger](https://exchange.api.xrocket.exchange/api/docs/) подключает
[swagger-ui-init.js](https://exchange.api.xrocket.exchange/api/docs/swagger-ui-init.js),
в котором встроен `swaggerDoc`. Conventional Nest URL
[docs-json](https://exchange.api.xrocket.exchange/api/docs-json) проверен HTTP200;
его parsed JSON **совпал** со встроенной схемой. Это проверенный URL, а не вывод
о наличии API endpoint по соглашению об именах.

Неизменённые HTTP response bytes сохранены в
[exchange-current.json](openapi/exchange-current.json): 174290 bytes,
SHA-256 `71d4ef2e77273606ab63959434e8ad9007c3f8268d4e8ef2a647e2c9d112f969`.
OAS `3.0.0`, `info.version=1.0.0`, 23 paths / 26 REST operations / 53 schemas.
[Manifest](openapi/manifest.json) содержит URL, UTC timestamp, локальную дату,
content type, размер, hash и discovery chain. UTC дата получения 17 октября
соответствует 18 октября в Asia/Tashkent. Snapshot не форматировался и не исправлялся.
Pay Current/Legacy snapshots и их метаданные сохранены.

[Source ledger](exchange-sources-2026-10-18.json) фиксирует проверенные официальные
HTML URL, получение HTTP200, hashes и существующие heading anchors. Это provenance
публичной документации, не обещание стабильности её HTML. Initial shell fetch
получил sandbox WinError10013; разрешённое чтение с default urllib UA дало HTTP403.
Повтор с `httpx` и `User-Agent: Mozilla/5.0` прошёл. Никакие реальные credentials
или приватные business endpoints не использовались. Доступность testnet API,
фактические REST payloads и WebSocket connection в X001 не проверялись.

## Окружения и авторизация

| Что доказано документацией | Значение / граница |
|---|---|
| Production REST | `https://exchange.api.xrocket.exchange` |
| Testnet REST | `https://exchange.api.testnet.xrocket.exchange` |
| Старый Trade API | `https://trade.xrocket.exchange/api` deprecated/unsupported; не входит в snapshot |
| Private auth | `Authorization: Bearer <Exchange account token>`; отдельный bot Exchange settings token |
| OAS auth | `components.securitySchemes.bearer`: HTTP bearer, `bearerFormat: JWT`; root security отсутствует |
| Environments | Mainnet/testnet имеют разные accounts/tokens; переносить credentials между ними нельзя |

URLs и Bearer подтверждены [reference](https://docs.xrocket.exchange/api/exchange/reference/exchange-rest-api#base-url),
разделением accounts/tokens — [testing guide](https://docs.xrocket.exchange/api/exchange/guides/getting-started/testing).
`servers: []` в OAS не задаёт origins. `bearerFormat: JWT` — metadata, а не
контракт проверки JWT syntax, claims, expiry или signing key в SDK.
[Account setup](https://docs.xrocket.exchange/api/exchange/guides/getting-started/account-setup#authorization)
описывает account token без ограничиваемых permissions и invalidation старого
при renewal. X001 не создаёт и не обновляет token.

В OAS 10 операций без security (9 market/rates + health) и 16 с bearer.
Отсутствие security при отсутствующем root requirement означает public по схеме;
это не live наблюдение. Reference не помечает trade fees и withdrawal quotas как
private, но их OAS операции содержат `security: [{"bearer": []}]`: **EX-001**,
требуется отдельное уточнение, не включать их в первый public срез.

## REST inventory и HTTP shapes

Полный [inventory](exchange-rest-inventory.md) перечисляет все 26 method/path,
operationId, auth, response и queue owner. Owner — planned coverage, включая
будущие contract gates; это не признак наличия метода SDK. WebSocket туда не входит.
Обычные read responses — непосредственные product objects/collections, без
Pay cursor envelope. Money/price/size обычно decimal strings; массивы и поля
сверяются с конкретным DTO, общий Pay parser по сходству не переносится.

По OAS все GET и DELETE order возвращают 200, четыре POST (orders, estimate,
transfer, withdrawal) — 201. DELETE order возвращает JSON `CancelOrderResponse`,
не пустой ответ. Схема error responses индивидуальна по операции; факт отсутствия
401/429 в operation responses не доказывает невозможность этих HTTP статусов.

Истории orders/transfers/withdrawals используют `currentPage` (default1),
`pageSize` (default20, maximum100), optional date-time `startAt/endAt` и собственные
коллекции с required `currentPage/pageSize/totalNum/totalPage` (`type: number`).
Minimum/integer constraints и terminal-page protocol не определены. Отдельная
Exchange page, без Pay cursor, auto-pagination и выдуманных bounds. Будущий history
caller явно фиксирует wire serialization `hideCanceled` в Exchange policy и тесте,
не полагаясь на неявный bool-to-string. Для первого symbols среза pagination нет.

## Ошибки

OAS error content type — `application/json`; problem-like objects содержат
required `type/title/status/detail/instance/kind`. `type` — path code вида
`/api/problems/exchange_symbol_not_found`, `status` — number, `kind` — строковая
категория; 400 может использовать `oneOf` с discriminator `type` и optional
variant-specific `info`. `ClientDataProblemValidationDto.errors` — map из arrays
строк или nested maps arrays строк. Не все examples содержат required `info`.
Проверяемые pointers: `paths["/api/v1/symbols/{symbol}"].get.responses[400,404,500]`,
`paths["/api/v1/orders"].post.responses["400"]`,
`components.schemas.ClientDataProblemValidationDto`.

[Error guide](https://docs.xrocket.exchange/api/exchange/guides/error-handling)
описывает HTTP400/401/403/404/429/500, 429 и `Retry-After`, но не точные quotas.
Guide client-validation example имеет `kind: validation`, OAS generic validation —
`client_data_validation`; другие business variants самой OAS используют
`validation`. **EX-002**: не закрывать `kind` одним enum и не классифицировать
успех по тексту поля. Наличие duplicate client-ID error не доказывает безопасный
retry или срок deduplication. Retry/backoff guide — совет приложению, не новый
автоматический retry policy SDK.

Для первого среза существующий core сохраняет object `APIError.problem`, HTTP
status, `x-request-id` и `retry-after`; статусы классифицируются transport-слоем,
raw problem не печатается в message. Нельзя обещать, что сервер всегда отправит
эти headers или RFC-compliant problem. Unknown/non-JSON errors остаются ошибками
со статусом; строгие Exchange problem DTO/exception subclasses пока не нужны.

## Выбранный следующий результат: X002

[X002](../workflow/tasks/X002.md) — **только symbols list/retrieve** плюс минимальные
самостоятельные sync/async Exchange clients. План public surface:
`ExchangeClient` / `AsyncExchangeClient`, `symbols.list()` → `SymbolsResponse`,
`symbols.retrieve(symbol=...)` → `Symbol`. Имена здесь — SDK design decision.

| Operation | Подтверждённый контракт |
|---|---|
| GET `/api/v1/symbols` | Нет parameters/security; exact200 `{symbols: SymbolResponse[]}`; required `symbols`; 500 problem |
| GET `/api/v1/symbols/{symbol}` | Required string path `symbol`, без schema length/pattern; exact200 прямой `SymbolResponse`; 400 unavailable, 404 not found, 500 problem |

Pointers: `paths` этих двух путей, `components.schemas.SymbolResponse` и
`SymbolsResponse`; [list reference](https://docs.xrocket.exchange/api/exchange/reference/http/exchange-market-data-controller-get-symbols),
[retrieve reference](https://docs.xrocket.exchange/api/exchange/reference/http/exchange-market-data-controller-get-symbol).

`SymbolResponse` required: `symbol/baseAsset/quoteAsset`, `baseMinSize/quoteMinSize`,
`baseMaxSize/quoteMaxSize`, `minPrice/maxPrice`, `baseIncrement/quoteIncrement/priceIncrement`,
`enableTrading`, `precisions`, `labels`. Числовые quantities/prices/increments и
`precisions[]` передаются strings; `enableTrading` — boolean; `labels[]` — strings
с перечисленными known labels new/xrock/contest/featured/delisting_warning/delisting.
`openTime` — optional **plain string**, format/date-time и nullable не объявлены.

Выбранные SDK policies для X002, а не новые upstream guarantees: snake_case aliases,
собственные Exchange DTO, finite exact Decimal из decimal strings без float
промежутка для quantities/prices/increments/precisions; strict bool; unknown
fields/labels сохраняются. Missing `openTime` допускается, present string хранится
без datetime coercion; explicit null не выводится из omission. Path segment
кодируется целиком; dot segments не могут нормализовать маршрут. Непустота/dot
guard, если нужны для безопасного формирования URL, явно документируются как SDK
policy. Не uppercase/strip/normalize symbol и не вводить бизнес-лимиты из примера.

Client lifecycle/HTTP pooling/ownership и внедряемая sync/async сессия следуют
существующему transport contract, но Exchange origins, tokens и DTO принадлежат
Exchange. Public запросы без token удаляют default Authorization/auth внедрённого
клиента, как уже умеет core; Pay client/session автоматически не переиспользуется.
Первый срез не даёт private API, retries, streaming, live requests или pagination.

## Shared core: что менять и что оставить

Для двух symbols GET **изменение core не обосновано**: пути начинаются `/api/`,
метод GET уже поддержан, `request(..., success_statuses=(200,))` даёт exact200,
TypeAdapter декодирует product DTO, ошибки сохраняют problem object. Dynamic
path parameter готовит Exchange resource; новый origin передаёт Exchange client.
Decimal/aliases/omission/unknown fields остаются Exchange model policy, Pay DTO
и cursor нельзя импортировать ради повторного использования.

Будущие конкретные контракты тоже не требуют общего rewrite сейчас: DELETE order
имеет JSON200 (адаптер уже поддержан), POST201 поддержан; `oneOf`/asset maps —
продуктовые DTO; repeated query arrays допустимы как list tuples в core, а wire
encoding arrays нужно отдельно сверять. Пагинация и bool query — Exchange layer.
WebSocket heartbeat/auth/subscribe/reconnect — отдельный protocol/lifecycle,
не HTTP transport. Если gate выявит реальную нехватку core, нужна узкая отдельная
карточка с сохранённым контрактом и Pay regression tests.

## Противоречия и границы продолжения

| ID | Что известно / что не доказано | Следующий owner |
|---|---|---|
| EX-001 | Reference auth labels расходятся с bearer OAS у fees/quotas | X010 / X012 contract gates |
| EX-002 | `kind` и required `info` не согласованы между guide/schema/examples | Product readers сохраняют raw; X010–X013 уточняют нужные variants |
| EX-003 | `/health` есть в OAS, отсутствует в reference method table; schema требует status/info/error/details | X009; Pay live omission override не переносится |
| EX-004 | openTime — string без format; candles/orderbook positional arrays с недостаточно строгими item schemas | X002 хранит string; X005/X006 фиксируют tuples по фактам и документируют пределы |
| EX-005 | JWT metadata, quotas, array encoding acceptance, numeric page bounds, stable ordering/terminal pages, duplicate-ID retention/replay и timeout outcome live не проверены | Соответствующие future cards; без скрытых retries/lookup |
| EX-006 | WS pong/reconnect/resume/backpressure/orderbook gap semantics не определены | [WS spec](exchange-websocket.md), X014 |

X003–X009 — отдельные небольшие public resources; X010 (account), X011 (orders),
X012 (funding), X013 (transfers), X014 (WebSocket) — самостоятельные **contract
gates**, не обещание реализации всей категории за сессию. Их результат — уточнённый
контракт и разбиение на следующие implementation cards с передачей ownership без
дубликатов. Все новые карточки todo и **вне сохранённого scope autopilot**; здесь
они не выполняются. Первая доступная после X001 — X002. Push/review и управление
scope остаются координатору, расширение сохранённого scope автоматически не разрешено.
