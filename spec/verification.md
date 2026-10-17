# Проверка первого среза

Дата: 17.10.2026. Окружение: Windows, Python 3.12.14, HTTPX 0.28.1,
Pydantic 2.14.1. Полный набор версий — `requirements-dev.lock`.

| Проверка | Результат |
|---|---|
| `python -m pytest -q` | 156 passed, 2 live tests deselected |
| `python -m pytest -m live -q` с `XROCKET_RUN_LIVE=1` | 2 passed, публичный testnet |
| `python -m ruff check .` | Passed |
| `python -m mypy` | Passed, strict, 13 source files |
| `python -m build --no-isolation` | Собраны wheel и sdist, версия 0.1.0.dev0 |
| `pip install --no-build-isolation --no-deps -e .` | Passed; импорт установленного пакета проверен |

Unit tests проверяют шесть GET операций с MockTransport для обоих клиентов,
Decimal precision, response aliases, unknown statuses/fields, nullable expiration,
timezone, курсоры и отсутствие лишних запросов. HTTP checks покрывают ошибки,
не-JSON ответы, timeout, отсутствие retries/redirects, конфигурацию URL,
владение сессиями и изоляцию авторизации от внедрённого HTTP-клиента.

Live tests выполнены без токена и без изменения данных:

- `GET https://pay.api.testnet.xrocket.exchange/api/v1/currencies`
- `GET https://pay.api.testnet.xrocket.exchange/api/v1/rates?base=USD&assets=BTC&assets=ETH`

Подтверждены response models этих двух запросов, optional auth rates в testnet
и повторяющиеся query keys `assets`. Цены не фиксируются: проверяются валюты,
формат, конечность и положительность курса.

Не проверены живые приватные endpoints: нет предоставленного testnet JWT.
Остальные 19 из 25 Pay операций ещё не реализованы. Write, webhook verification,
Legacy и Exchange пока относятся к проектированию. Mainnet и матрица Python
3.11/3.13+ не запускались. Результат зелёных mock tests не распространяется
автоматически на эти области.
