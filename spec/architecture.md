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
  _core/                 # HTTP и базовые ошибки, без знания Pay/Exchange
  pay/
    client.py            # PayClient / AsyncPayClient, конфигурация ресурсов
    models/
      __init__.py        # стабильные re-exports моделей
      _base.py           # response config и Money, только для Pay
      pagination.py      # CursorPagination / CursorPage, только для Pay
      app.py             # AppInfo / Balance / AppBalances
      currencies.py      # Currency / CurrencyNetwork
      health.py          # Health / HealthComponent
      rates.py           # Rate
      invoices.py        # Invoice и вложенные response DTO
      invoice_payments.py # платежи invoice, transaction types и отдельная page
    resources/           # app, currencies, health, rates, invoices
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
Для будущих больших write-payload: отдельные request models/TypedDict. Аргументы
бизнес-запроса не смешиваются с transport options. Для первого среза достаточно
timeout в конструкторе; API per-request options появится вместе с реальной нуждой.

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
