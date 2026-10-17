# Сравнение архитектур Python SDK

Дата исследования: 2026-10-17. Статус: архитектурное предложение для обсуждения.

Задача xRocket SDK: сначала реализовать Pay, затем добавить Exchange без перестройки публичного API и без смешивания двух продуктов в одном большом клиенте. Ниже сравниваются официальные SDK Stripe, OpenAI и Coinbase, а также CCXT как крупная библиотека для работы с биржами. CCXT не является официальным SDK xRocket или какой-либо одной биржи.

Исследованы README и исходники основных веток репозиториев. Ссылки на `main`/`master` изменяемые; они подтверждают наблюдения на дату исследования. Для воспроизводимого аудита зависимостей перед релизом нужны конкретные версии и commit SHA.

## Что устроено в других библиотеках

| Библиотека | Публичный API и внутреннее устройство | Полезно для xRocket | Ограничения и антипаттерны для нашей задачи |
| --- | --- | --- | --- |
| Stripe Python | `StripeClient → v1/v2 → service → _APIRequestor → HTTPClient`. Например, `client.v1.customers.retrieve(...)`. Async-операции расположены на тех же services и имеют суффикс `_async`. | Ресурсные пространства, тонкие services, общий request pipeline, отдельные параметры операции и request options, доступ к HTTP metadata. | Не переносить глобальную конфигурацию legacy API и поддержку множества HTTP backend без доказанной необходимости. Суффиксы `_async` удваивают список методов на каждом ресурсе. |
| OpenAI Python | Отдельные `OpenAI`/`AsyncOpenAI`, ресурсные классы `Models`/`AsyncModels`, общий `BaseClient`; вложенные request parameters через `TypedDict`, response models через Pydantic. | Одинаковые названия sync/async операций, разделение клиентов, типизация вложенных моделей, контекстные менеджеры, внедряемый HTTP-клиент. | Политика повторов другого API не определяет безопасность повторов переводов и платежей xRocket. Не переносить streaming/raw wrappers до появления реальной потребности. |
| Coinbase Advanced Python | Отдельные пакеты REST, WebSocket и других API. `RESTClient` наследует `RESTBase` и импортирует endpoint-функции из предметных файлов в один класс. REST transport использует `requests.Session`. | Разделение продуктов и протоколов внутри одного дистрибутива; предметные файлы операций; повторное использование HTTP-сессии. | Плоский клиент с большим числом методов сложнее расширять. README прямо оговаривает неполную типизацию вложенных response fields: часть требует обращения как к словарю. |
| CCXT | Унифицированная Exchange-база, отдельный Python namespace `ccxt.async_support`; async transport использует aiohttp. Есть rate limiter и иерархия сетевых/биржевых ошибок. | Классификация ошибок, внимание к точности денежных значений, ограничение запросов и управление временем жизни соединений. | Многотысячная универсальная база и большой конфигурационный словарь оправданы множеством бирж. Для двух продуктов одного сервиса такая универсальность создаст лишние связи. |

### Первичные источники

Stripe:

- [README: клиент, request options, HTTP clients, retries, typing, async](https://github.com/stripe/stripe-python#readme).
- [StripeClient: создание requestor и пространств v1/v2](https://github.com/stripe/stripe-python/blob/master/stripe/_stripe_client.py).
- [InvoiceService: методы create и create_async](https://github.com/stripe/stripe-python/blob/master/stripe/_invoice_service.py).
- [Общий API requestor](https://github.com/stripe/stripe-python/blob/master/stripe/_api_requestor.py).

OpenAI Python:

- [README: sync/async, типы, пагинация, ошибки и настройка HTTP](https://github.com/openai/openai-python#readme).
- [Отдельные клиенты](https://github.com/openai/openai-python/blob/main/src/openai/_client.py).
- [Ресурсы Models и AsyncModels](https://github.com/openai/openai-python/blob/main/src/openai/resources/models.py).
- [BaseClient и объекты страниц](https://github.com/openai/openai-python/blob/main/src/openai/_base_client.py).

Coinbase:

- [README: структура API и ограничения вложенных response types](https://github.com/coinbase/coinbase-advanced-py#readme).
- [RESTClient и импорт предметных endpoint-функций](https://github.com/coinbase/coinbase-advanced-py/blob/master/coinbase/rest/__init__.py).
- [RESTBase: Session, HTTP-запросы и обработка ответов](https://github.com/coinbase/coinbase-advanced-py/blob/master/coinbase/rest/rest_base.py).

CCXT:

- [README: Python и async_support](https://github.com/ccxt/ccxt#python).
- [Синхронная Exchange-база и rate limiter](https://github.com/ccxt/ccxt/blob/master/python/ccxt/base/exchange.py).
- [Асинхронная база, aiohttp и закрытие сессий](https://github.com/ccxt/ccxt/blob/master/python/ccxt/async_support/base/exchange.py).
- [Иерархия ошибок](https://github.com/ccxt/ccxt/blob/master/python/ccxt/base/errors.py).

## Предлагаемые решения для xRocket

Это собственные выводы из сравнения. Их следует согласовать с контрактами Pay и Exchange; они не являются требованиями перечисленных библиотек.

| Вопрос | Предложение | Причина |
| --- | --- | --- |
| Packaging | Один Python-дистрибутив, пространства `xrocket.pay` и `xrocket.exchange`. | Общие установка и релиз, понятные продуктовые границы. Пока размер проекта не оправдывает отдельные пакеты и независимые версии. |
| Клиенты | `PayClient`/`AsyncPayClient`; в следующем этапе `ExchangeClient`/`AsyncExchangeClient`. | Sync-код не делает скрытых переходов в event loop. Async-код не получает блокирующих операций под тем же именем. |
| Resources | Например, будущие `pay.invoices.create(...)`, `pay.payouts.create(...)` (имя payouts соответствует Current OAS). | Имена группируются по предметной области, клиент не превращается в плоский каталог операций. |
| Общий код | Приватный `_core` для HTTP infrastructure, options, response metadata и базовых ошибок. | Pay и Exchange используют инфраструктуру, сохраняя собственные контракты. |
| Продуктовые различия | Credentials, base URL, auth, API envelope, модели и правила пагинации принадлежат продукту. | Общая инфраструктура не должна предполагать одинаковую авторизацию или формат ошибок. |
| HTTP | Один выбранный backend: HTTPX с `Client`/`AsyncClient`, возможность передать свой клиент. | Повторное использование соединений и удобная подмена transport в тестах без поддержки нескольких backend. |
| Типы | Явные keyword-only параметры; `TypedDict` для сложных входных структур; полные Pydantic-модели ответов. | Автодополнение и проверка вложенных полей без интерфейса на основе `dict[str, Any]`. |
| Деньги | `Decimal` внутри SDK; сериализация по подтвержденному контракту API. | Исключение дополнительной потери точности из-за промежуточного преобразования через `float`. |
| Ошибки | Общий `XRocketError`, затем сетевые и API ошибки; сохранять HTTP status, API code, request ID и исходную причину, когда они есть. | Предсказуемые обработчики исключений без потери диагностики. |
| Повторы | Политика задается для конкретных операций. Автоповторы write-запросов только при подтвержденной безопасности/idempotency. | Повтор после timeout может продублировать уже выполненную денежную операцию. |
| Пагинация | Явная страница как основной результат; отдельный iterator после проверки правил конкретного endpoint. | Нет скрытых дополнительных запросов и предположений об общей схеме offset/cursor. |
| Lifecycle | `with`/`async with`, явное закрытие; документировать владение переданным HTTP-клиентом. | Предсказуемое освобождение соединений и отсутствие закрытия чужой сессии. |
| Тестирование | Общие контрактные сценарии для sync/async, mock transport, проверка serialization/auth/errors/retries. | Проверяется наблюдаемое HTTP-поведение и отсутствие расхождений двух интерфейсов. |

HTTPX здесь — выбранная зависимость нашего SDK. Актуальный на дату исследования `openai-python/main` в README уже указывает HTTPX2; утверждать, что текущая версия OpenAI SDK использует обычный HTTPX, некорректно. Заимствуется организация слоев и клиентов, а не набор зависимостей.

Важная деталь реализации: продуктовые credentials передаются только запросам соответствующего клиента. При использовании общей HTTP infrastructure нельзя класть Pay token или Exchange authorization в общие изменяемые headers двух продуктов.

## Рекомендуемая структура

```text
src/xrocket/
  __init__.py
  py.typed
  _core/
    transport.py
    options.py
    errors.py
    response.py
  pay/
    __init__.py
    client.py
    async_client.py
    resources/
      invoices.py
      transfers.py
      ...
    models/
    webhooks.py
  exchange/                 # граница будущего модуля

tests/
  unit/
  contract/
  integration/
```

`exchange/` обозначает архитектурную границу следующего этапа, а не обязательство сейчас создавать заглушки операций. Ресурсы Pay добавляются по фактическому endpoint inventory. Логику webhook следует выделять только при подтвержденном документированном контракте.

```python
from xrocket.pay import PayClient, AsyncPayClient

with PayClient(api_token="...") as pay:
    invoice = pay.invoices.create(...)

async with AsyncPayClient(api_token="...") as pay:
    invoice = await pay.invoices.create(...)
```

Это эскиз интерфейса, а не исполняемый пример с окончательными параметрами. Модели запросов/ответов и правила HTTP должны быть общими для sync и async. Тонкие ресурсные wrappers могут быть отдельными: небольшое явное дублирование `def`/`async def` предпочтительнее метапрограммирования, которое ухудшит typing и чтение кода.

Корневой фасад вида `XRocket(pay=..., exchange=...)` можно добавить позднее как удобную композицию. Для первого релиза он не нужен: прямые клиенты уже сохраняют границы двух продуктов и не требуют инициализировать Exchange при работе с Pay.
