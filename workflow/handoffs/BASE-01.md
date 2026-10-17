# BASE-01: исследование API и первый read-only срез

Дата: 2026-10-17. Итог: done. Историческая передача предыдущей сессии, составлена
по проверенным файлам и результатам в чате; ниже не новые запуски текущей сессии.

## Результат

Создан `xrocket-sdk/`: pyproject, src/xrocket, tests, specs, окружение и lock.
Реализованы PayClient/AsyncPayClient и шесть GET: app info/balances, currencies,
rates, invoice list/retrieve. Есть typed nested models, Decimal, aware dates,
страницы, HTTP errors, timeout, ownership, auth isolation. Exchange — namespace.

Первые правила API и сравнение Stripe/OpenAI/Coinbase/CCXT записаны в spec.
Главная docs ведёт в Legacy; для интеграции выбран Current. Сырые Current/Legacy
схемы сохранены с SHA-256. Known issues PAY-001…017 перечислены в pay-api.md.

## Подтверждённые проверки предыдущей сессии

| Команда | Результат |
|---|---|
| `.venv/Scripts/python.exe -m pytest -q` | 156 passed, 2 live deselected |
| `.venv/Scripts/python.exe -m pytest -m live -q -p no:cacheprovider`, XROCKET_RUN_LIVE=1 | 2 passed, 156 deselected |
| `.venv/Scripts/python.exe -m ruff check .` | Passed |
| `.venv/Scripts/python.exe -m mypy` | Passed, strict, 13 source files |
| `.venv/Scripts/python.exe -m build --no-isolation` | Wheel/sdist 0.1.0.dev0 собраны |
| `.venv/Scripts/python.exe -m pip install --no-build-isolation --no-deps -e .` | Passed, import/version проверены |
| SHA256 snapshots + wheel content (py.typed/client.py) | Passed |

Live GET только testnet currencies/rates без токена. Для base=USD и assets=BTC,
assets=ETH подтверждены optional auth и повторяющиеся keys. Private/mainnet live
не проверены. Подробнее: `spec/verification.md`.

## Ограничения и следующий шаг

19 Pay операций, writes, webhooks и Exchange ещё не реализованы. Transport только
GET и /api paths; models.py пока единый. Не было реальных платежей или публикации.
Git не инициализирован, commit отсутствует. Подготовка workflow — FLOW; следующая
реализация выбирается через tasks.json, первоначально P001 (организация моделей).
