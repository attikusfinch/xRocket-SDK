# План реализации и проверки

## Этап 0 — контракт и runnable skeleton (текущий)

- Зафиксировать Current/Legacy OpenAPI и provenance, выбрать Current-only.
- Проверить границы Pay/Exchange и сравнить архитектуры официальных Python SDK.
- Проверить общий HTTP pipeline на read-only ресурсах Pay: app info, balances,
  currencies, rates, list/retrieve invoices. Без write-запросов.
- Одна таблица контрактов для sync/async: verb, path, auth, query names/encoding,
  форма ответа. MockTransport выполняет все unit tests без сети и токенов.
- Проверить точность денег, будущие поля/статусы, nullable expiration, пустые
  коллекции, страницы и обе формы invoice ID.
- Проверить 400/401/403/404/429/500, не-JSON errors, malformed success, timeout,
  redirect, отсутствие токена, lifecycle внедрённой и собственной сессии.
- Проверить lint, strict typing и сборку wheel/sdist.

Fixtures — синтетические примеры из контракта, а не записанные ответы аккаунта.
Зелёные mock tests подтверждают работу SDK с выбранным контрактом, но сами по себе
не доказывают совместимость реального сервера. Снимок OAS не является текущим
ответом production API и не обновляется автоматически во время тестов.

## Этап 1 — завершить чтение Pay

Добавить cheques, payouts, withdrawals, quotas, invoice payments и health.
Покрыть все nullable transaction fields и union types. Отдельно уточнить
`rates` optional auth, encoding query arrays и ограничения limit.
Read-only smoke по testnet с токеном из переменной окружения — отдельная задача;
токен не нужен для обычного запуска тестов.

## Этап 2 — write и webhooks

1. Invoice create/delete и payment address; клиентские условия priceAmount/minPayment.
2. Cheques и webhook verification Current v1: raw bytes, HMAC, compare_digest,
   timestamp в ms, configurable replay window. Unknown events сохраняются,
   повторная доставка и out-of-order события документируются.
3. Payouts, mass payouts (partial success), withdrawals, withdrawal links.
4. Контракт идемпотентности, поведение duplicate client ID и timeout после commit
   проверяются на testnet до автоматических повторов записей.

Денежные end-to-end tests запускаются отдельно на testnet с явными входными данными.
Текущий проект таких тестов и методов записи пока не содержит.

## Этап 3 — Exchange

Сначала новая зафиксированная OAS и public REST data, затем account/orders/funding,
после — отдельный WebSocket-клиент. Проверить, что новый продукт не требует правок
Pay resources/models и не переносит Pay credentials в свои запросы. Биржевая
пагинация, reconnect, snapshots/deltas и order lifecycle получают свои контракты.

## Обычный запуск

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m build --no-isolation
```

Опциональный сетевой smoke запускается только явно:

```powershell
$env:XROCKET_RUN_LIVE = '1'
.venv\Scripts\python.exe -m pytest -m live
```

Он обращается к публичным currencies/rates testnet, не требует токена и не пишет
данные. Недоступность testnet — failure интеграции, а не причина маскировать её
как успешный unit test.
