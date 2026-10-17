# Exchange WebSocket: исследованный контракт

Проверено **2026-10-18, Asia/Tashkent** по официальной документации. Это результат
исследования X001, а не реализованный SDK API. REST, его snapshot и provenance —
в [exchange-api.md](exchange-api.md). Следующая граница WebSocket — самостоятельная
[X014](../workflow/tasks/X014.md): сначала закрыть контрактные вопросы, затем отдельно
планировать реализацию. Наличие REST OpenAPI не задаёт WebSocket контракт.

## Подтверждённый lifecycle

Официальные [connection](https://docs.xrocket.exchange/api/exchange/websocket#how-to-connect),
[authentication](https://docs.xrocket.exchange/api/exchange/websocket#authentication),
[message format](https://docs.xrocket.exchange/api/exchange/websocket#message-format)
и [methods](https://docs.xrocket.exchange/api/exchange/websocket#methods):

| Этап | Документированный факт |
|---|---|
| Connect | Production `wss://exchange.app-api.xrocket.exchange/`; testnet `wss://exchange.app-api.testnet.xrocket.exchange/`. |
| Authenticate | Private channels требуют `auth` с `params.token` до подписки; public channels доступны без auth. Успех показан как `result.success: true`. |
| Keepalive | JSON request `{"id":"unique-id","method":"ping"}` каждые 30 секунд; idle connection закрывается сервером через 60 секунд. |
| Correlation | Каждый request имеет уникальный `id` типа string или number; он связывает response с request. |
| Subscribe | `method: "subscribe"`, `params.channel` и параметры канала. Push использует `method: "subscription"`, `params.channel` и `params.data`. |
| Unsubscribe | Есть `unsubscribe` с `params.channel`, а также `unsubscribeAll`. Точная идентичность подписки при нескольких symbol/interval не определена. |
| Errors | [Формат](https://docs.xrocket.exchange/api/exchange/websocket#error-response-format): `id`, `error.code`, `error.message`, `error.data`; в примере data содержит detail. |

[Error codes](https://docs.xrocket.exchange/api/exchange/websocket#our-error-codes)
включают `-32002` already subscribed, `-32003` not subscribed, `-32030` invalid token,
`-32033` unauthorized, `-32034` user blocked и `-32050` rate limit exceeded.
Документация относит error codes к JSON-RPC; примеры не устанавливают требование
поля `jsonrpc: "2.0"` для сообщений.

## Каналы и начальные данные

Это inventory документированных каналов; SDK методы и DTO здесь не объявляются.
Общие правила public/private также перечислены в официальном
[channels overview](https://docs.xrocket.exchange/api/exchange/websocket#channels).

| Канал | Параметры и подтверждённое поведение |
|---|---|
| [ticker](https://docs.xrocket.exchange/api/exchange/websocket/public-ticker#request-parameters) | Public; обязательные symbol и interval. Начальный ACK показывает success; push содержит data.ticker. |
| [allTickers](https://docs.xrocket.exchange/api/exchange/websocket/public-all-tickers#request-parameters) | Public; обязательный interval; push содержит data.tickers. |
| [orderbook](https://docs.xrocket.exchange/api/exchange/websocket/public-orderbook#request-parameters) | Public; обязательный symbol, дополнительные depth и precision. Начальный ответ описан как полный snapshot. |
| [trades](https://docs.xrocket.exchange/api/exchange/websocket/public-trades#request-parameters) | Public; обязательный symbol; push содержит data.trades. Поле side обозначает taker side. |
| [candles](https://docs.xrocket.exchange/api/exchange/websocket/public-candles#request-parameters) | Public; обязательные symbol и type. Optional snapshot.startAt/endAt добавляет историю в начальный ответ; без него начальных candles нет, updates продолжаются. |
| [balances](https://docs.xrocket.exchange/api/exchange/websocket/private-balances) | Private; ACK показывает только success, push — data.balances для одного или нескольких assets. Начальный полный account snapshot не обещан. |
| [activeOrders](https://docs.xrocket.exchange/api/exchange/websocket/private-active-orders) | Private; ACK показывает только success, push — data.orders. Описаны limit, market, stopMarket, stopLimit; начальный полный список orders не обещан. |

Для candles документирован позиционный порядок
`[start, open, close, high, low, baseVolume]`, отличающийся от обычного OHLCV;
см. [response parameters](https://docs.xrocket.exchange/api/exchange/websocket/public-candles#response-parameters).
Не переносить REST DTO или Pay pagination в эти сообщения автоматически.

## Противоречия и открытые вопросы для X014

- [Orderbook response](https://docs.xrocket.exchange/api/exchange/websocket/public-orderbook#response)
  описывает первый ответ как полный snapshot, последующие сообщения — incremental.
  Начальный result-пример не содержит snapshot, а push-пример содержит snapshot: true.
  [Таблица полей](https://docs.xrocket.exchange/api/exchange/websocket/public-orderbook#response-parameters)
  задаёт true как полный snapshot, false как increment и sequence как string.
  Семантика sequence gaps, resume/replay и удаления price levels не определена;
  нельзя проектировать восстановление стакана по одному примеру.
- В introduction и семи channel pages не найдены pong schema/deadline, close codes,
  reconnect/backoff/resubscribe protocol, delivery/order guarantees, backpressure,
  connection/subscription quotas. Это пробелы прочитанных источников, а не доказательство
  отсутствия возможностей сервера.
- Не определены повторная auth, истечение/отзыв токена на открытом соединении,
  начальное согласование private streams с REST состоянием и доставка terminal order events.
- У unsubscribe показан только channel; нужно выяснить адресацию нескольких подписок
  одного канала. Rate-limit error не задаёт численных квот или алгоритма retry.

X014 должна сохранить проверяемые ответы на эти вопросы либо явно ограничить будущий
scope. Reconnect, re-auth и resubscribe будут решениями SDK только после такой фиксации;
автоматические гарантии или безусловное восстановление здесь не обещаются. Transport,
credentials и lifecycle WebSocket проектируются отдельно от Pay и REST sessions;
изменения shared core допустимы только при конкретной подтверждённой потребности.

## Проверка источников

Все восемь страниц выше доступны при read-only HTTP GET с `User-Agent: Mozilla/5.0`;
проверены connection/auth/message/method/error anchors и содержимое channel pages.
Live WebSocket handshake, private auth и торговые/денежные операции не выполнялись.
Документ описывает опубликованный контракт, а не проверенное поведение сервера.
