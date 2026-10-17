# Зафиксированные источники

Дата загрузки: **2026-10-17**. JSON сохранены без изменений. Метаданные и SHA-256 —
в [manifest.json](manifest.json). Снимки нужны для воспроизводимого проектирования
и contract tests; текущий сервер может отличаться от них.

| Файл | Источник | Версия из `info` | Использование |
|---|---|---|---|
| [pay-current.json](pay-current.json) | [Current OAS](https://pay.api.xrocket.exchange/api/docs-json) | 1.0.0 | Целевой Pay API, 25 операций |
| [pay-legacy.json](pay-legacy.json) | [Legacy OAS](https://pay.xrocket.exchange/api-json) | 1.3.1 | Сравнение миграции, 20 операций |

Одинаковая/большая цифра версии не означает более новый контракт: Legacy 1.3.1
и Current 1.0.0 — разные API. Выбирать API по сравнению этих чисел нельзя.

Current OAS не содержит base URLs (`servers: []`). Они взяты из раздела
[Pay REST API](https://docs.xrocket.exchange/api/pay/reference/pay-rest-api):

- Mainnet: `https://pay.api.xrocket.exchange/`
- Testnet: `https://pay.api.testnet.xrocket.exchange/`

Из narrative-документации не переносим примеры с `.pp` и `/transfer`: список
методов сверяется с живой Current OAS (`/payouts`). Подробности и открытые вопросы —
в [контракте Pay](../pay-api.md). Полная Exchange OAS будет зафиксирована на этапе
Exchange; пока исследована граница REST/WebSocket и пагинация по официальной
[Exchange reference](https://docs.xrocket.exchange/api/exchange/reference/exchange-rest-api).
