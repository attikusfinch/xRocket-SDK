# Архитектура Python SDK

Статус: проект решения для обсуждения, проверенный первым read-only срезом.
Исследование API: 17 октября 2026 года. Python 3.11+; рабочее имя дистрибутива
`xrocket-sdk`, import namespace `xrocket`. Доступность имени в PyPI пока не проверена.

## Границы модулей

Один дистрибутив содержит независимые продукты `xrocket.pay` и `xrocket.exchange`.
Пользователь импортирует только нужный клиент. Pay работает с приложением мерчанта,
Exchange — с торговым аккаунтом, market data и WebSocket. Даже при одинаковой Bearer
схеме токены и HTTP-сессии продуктов не объединяются автоматически.

```text
src/xrocket/
  _core/                 # HTTP, request serialization и ошибки, без знания Pay/Exchange
  pay/
    client.py            # PayClient / AsyncPayClient, конфигурация ресурсов
    models/
      __init__.py        # стабильные re-exports моделей
      _base.py           # response config и Money, только для Pay
      pagination.py      # CursorPagination / CursorPage, только для Pay
      payouts.py         # Payout / PayoutCallback, amount через Money
      app.py             # AppInfo / Balance / AppBalances
      cheques.py         # Cheque / ChequeLinks / ChequeCallback / ChequeURL
      currencies.py      # Currency / CurrencyNetwork
      health.py          # Health / HealthComponent
      rates.py           # Rate
      withdrawals.py     # Withdrawal / WithdrawalCallback / WithdrawalQuotas
      invoices.py        # Invoice и вложенные response DTO
      invoice_payments.py # платежи invoice, transaction types и отдельная page
      invoice_requests.py # отдельные InvoiceCreate/Callback/URL/CustomerRequest
      cheque_requests.py # отдельные ChequeCreate/Update/Callback/URLRequest
    resources/           # app, cheques, currencies, health, rates, invoices, payouts, withdrawals
  exchange/              # зарезервирован; исполняемого клиента пока нет
  py.typed
```

Зависимости направлены от продукта к `_core`. `_core` не импортирует продукты,
Pay не импортирует Exchange. Модели разделены по существующим ресурсам; базовая
response-модель, денежный тип и cursor pagination остаются внутри Pay. Новые
ресурсы добавляют свои DTO по мере реализации, без пустых модулей заранее.
Прежние импорты моделей из `xrocket.pay.models` и `xrocket.pay` сохранены и
возвращают те же классы; `Money` по-прежнему доступен из `xrocket.pay.models`.
Ресурсы используют эти re-exports; DTO зависят только от Pay `_base` и своих
вложенных моделей. Полные каталоги будущих ресурсов описаны в
[контракте Pay](pay-api.md).

В Exchange появятся собственные REST-ресурсы и отдельный WebSocket-клиент.
Реконнект, heartbeat, восстановление подписок, backpressure и последовательность
событий не входят в HTTP transport. Типы `PayInvoice` и будущего биржевого `Order`
не сводятся к общему абстрактному объекту сделки.

## Public API

```python
from xrocket.pay import PayClient, AsyncPayClient

with PayClient(api_token=token, environment="testnet") as pay:
    balances = pay.app.balances()
    page = pay.invoices.list(limit=100)
    for invoice in page.items:
        print(invoice.id, invoice.price_amount, invoice.status)
    if page.pagination.next is not None:
        next_page = pay.invoices.list(cursor=page.pagination.next, limit=100)

async with AsyncPayClient(api_token=token, environment="testnet") as pay:
    balances = await pay.app.balances()
```

Имена методов и модели результатов совпадают для sync и async. Код ресурсов
прямолинеен, без метаклассов, динамического `__getattr__` и запуска async через
вложенный event loop. Небольшое повторение thin resource methods допустимо;
таблица контрактных тестов проверяет обе версии одним набором сценариев.

Используем keyword-only параметры, snake_case в Python и camelCase в wire format.
Для больших write-payload используются отдельные request models. Аргументы
бизнес-запроса не смешиваются с transport options. Для первого среза достаточно
timeout в конструкторе; API per-request options появится вместе с реальной нуждой.

Фундамент записи P008 находится во внутреннем `_core`; P009 использует его
для invoice create/delete. `serialization.RequestModel` отделён от response models:
extra запрещены, instances повторно валидируются перед отправкой. Alias rules
задаёт продуктовый DTO, общий core не навязывает camelCase другим продуктам.
`RequestMoney` принимает finite Decimal/decimal string и сериализуется JSON string.
`serialize_request()` возвращает UTF-8 bytes с aliases и `exclude_unset=True`:
missing опускается, явный None остаётся null, включая вложенные request DTO.
Response BaseModel, даже внутри payload, не превращается в request автоматически.
Payload graph ограничен JSON primitives, finite Decimal, dict со строковыми ключами,
list/tuple, SecretStr и RequestModel. SecretStr по умолчанию маскируется;
продуктовый field serializer явно раскрывает требуемый секрет в контексте
`request_wire=True`, который задаёт только serialize_request. Неявных
dataclass/bytes/date converters нет; продуктовый
DTO готовит требуемое wire значение явно. Вложенные RequestModel проверяются
также внутри Any, без изменения исходных объектов и их missing/explicit состояния.
Обязательные validated fields не могут исчезнуть при exclude_unset даже после
model_construct с вручную заданным fields_set; они помечаются на нормализованной
копии, optional omission и исходный объект сохраняются.

InvoiceCreateRequest и вложенные Callback/URL/CustomerRequest — отдельные Pay
request models со strict типами и camelCase aliases. Только price_currency
обязателен; оба amount одновременно запрещены, ни один не требуется безусловно
из-за PAY-008. None defaults обозначают omission, explicit None отвергается
по non-nullable OAS. Ресурс принимает `create(request=...)`, возвращает Invoice
на 200; `delete(invoice_id=..., client_invoice_id=...)` ждёт пустой 200 и возвращает None.

Cheque request DTO живут отдельно от response и invoice inputs. Create требует
asset/amount, update разрешает только optional description (пустая строка очищает).
None означает только unset default; explicit null запрещён. Password — SecretStr,
repr и обычные dumps скрывают его; validation input удаляется из field/model errors.
Create/update возвращают Cheque на 200, delete ждёт пустой 200; все mutation paths
plural, identifiers update/delete передаются в query прежним cheque helper.

`SyncTransport.request()` / `AsyncTransport.request()` принимают GET/POST/PUT/DELETE,
явный tuple success_statuses и response adapter: TypeAdapter означает JSON decode,
None означает строго пустой body. Неожиданный 2xx вызывает ResponseValidationError,
non-2xx использует прежние API errors. `get()` сохраняет прежний API и все 2xx.
Write JSON отправляется как готовые bytes с application/json; framing отражает
реальную длину, чужие Transfer-Encoding/Content-Encoding defaults не наследуются.
Исходный внедрённый HTTP client не меняется. `/health` остаётся GET-only,
GET body не поддержан. Остальные endpoint-specific DTO и retry/idempotency policy —
следующие карточки, автоматических mutation retries или ID генерации нет.

## HTTP и владение ресурсами

HTTPX обеспечивает pooling, sync/async и подменяемый transport. SDK создаёт
долгоживущую сессию; новый HTTP-клиент на каждый запрос не создаётся. Созданную
сессию SDK закрывает через `close()`/`aclose()` и context manager. Переданная
пользователем сессия принадлежит пользователю: SDK её не закрывает и не меняет
её defaults. После закрытия SDK его методы больше не выполняют запросы.

`environment="mainnet" | "testnet"` выбирается явно, default — mainnet.
`base_url` допускает собственный HTTPS origin и HTTP loopback для локальных тестов.
В URL запрещены userinfo, query, fragment и path prefix. Redirects не следуются;
timeout задаётся явно и при внедрённой сессии. Токены не участвуют в `repr` или
строках SDK ошибок. Сетевые логи с Authorization SDK не ведёт.
Авторизация берётся только из `api_token` SDK: default Authorization и auth handler
внедрённой HTTP-сессии не используются. Это предотвращает случайную отправку токена
другого продукта в публичный Pay-запрос, сохраняя исходные настройки HTTP-сессии.

Автоповторы в первом срезе отключены. Позже retry policy разделим по операциям:
read-only GET может повторяться с ограниченным backoff/jitter; денежные записи
требуют подтверждённого серверного контракта идемпотентности. Сам факт наличия
`clientPayoutId` не доказывает безопасный повтор любого запроса. После timeout
write-запроса результат может быть неизвестен; его нужно сверять по клиентскому ID.

## Типы и ошибки

Ответы — Pydantic 2 models, вложенные объекты тоже типизированы, неизвестные поля
сохраняются (`extra="allow"`). Поля обязательны только когда это следует из
контракта, с явными исключениями для дефектов OAS. Известные статусы документируются,
но response `status` хранится как `str`, чтобы новое значение не ломало чтение.
Неизвестный статус сам по себе не означает успех.

Деньги — `Decimal`, исходные строки разбираются без промежуточного `float`.
`float`, `bool`, NaN и Infinity для денежных полей отвергаются. Будущая запись
принимает `Decimal | str` и отправляет десятичную строку; SDK не округляет за
пользователя. Timestamp — timezone-aware datetime; Current `expiresIn` в ms.

Общие SDK ошибки отделяют сеть, timeout, HTTP API error и нарушение формата ответа.
HTTP ошибки классифицируются по status, а problem details сохраняются для анализа
конкретной бизнес-ошибки. SDK не сводит ошибку к `False` и не теряет HTTP status,
если upstream вернул HTML вместо JSON. Детали ответа доступны явно, но не печатаются
автоматически в exception message.

Cursor pagination принадлежит Pay. Метод `list()` возвращает одну страницу,
дополнительных сетевых вызовов не делает. `pagination.next` сохраняется буквально;
`total` не нужен общей модели страницы (payments его не возвращает). Биржевые
`currentPage/pageSize` будут отдельным типом. Auto-iterator отложен до проверки
терминальных cursors, duplicate pages и поведения при изменениях данных.

## Генерация и версии

Сырые OAS сохранены без правок. Ручной public API предпочтителен слепой генерации:
в OAS есть ошибочные типы datetime/nullability и противоречия auth. Будущий generator
может создавать внутренние wire types/fixtures с проверяемыми patches, но не должен
переписывать вручную спроектированную поверхность клиента.

Версия пакета общая для Pay и Exchange. Изменения в любом public модуле учитываются
в changelog. До первого стабильного релиза API является draft; ни PyPI publication,
ни Exchange/Legacy support эта заготовка не обещает.

## Основания решений

Сравнение [Stripe, OpenAI, Coinbase и CCXT](sdk-comparison.md) описывает реальные
паттерны, которые мы перенимаем. Адреса продуктов, различие pagination и Exchange
WebSocket подтверждены официальными страницами:

- [Pay REST API](https://docs.xrocket.exchange/api/pay/reference/pay-rest-api)
- [Exchange REST API](https://docs.xrocket.exchange/api/exchange/reference/exchange-rest-api)
- [Exchange overview: REST и WebSocket](https://docs.xrocket.exchange/api/exchange/exchange-api-overview)
- [HTTPX clients](https://www.python-httpx.org/advanced/clients/)
- [HTTPX transports](https://www.python-httpx.org/advanced/transports/)
