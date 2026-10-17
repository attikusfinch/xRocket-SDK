# План реализации и проверки

## Состояние после P018, 2026-10-18

Все 25 операций сохранённого Current OAS реализованы у обоих клиентов. Таблица
[operation → API → tests/source](pay-operation-matrix.md) сверена с реальными
resources/DTO и синтетическими fixtures, а не только с `session.py` inventory.
Новый полный offline результат и точные ограничения — в
[readiness ledger](pay-readiness-2026-10-18.md); первый [verification.md](verification.md)
и [live журнал](live-verification.md) остаются историческими evidence.

Следующие этапы сохранены как структура плана. P018 завершает offline Pay scope;
live acceptance, replay/idempotency и остальные открытые API facts не закрыты.
X001 исследует Exchange отдельно и не выполняется в P018.

## Этап 0 — контракт и runnable skeleton (выполнен offline)

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

## Этап 1 — чтение Pay (реализовано, live private не подтверждено)

Добавлены cheques, payouts, withdrawals, quotas, invoice payments и health.
Nullable transaction overrides и union types проверены synthetic tests. Отдельно уточнить
`rates` optional auth, encoding query arrays и ограничения limit.
Read-only testnet harness реализован как отдельный opt-in запуск; private live
подтверждения требуют явных JWT/fixtures. Токен не нужен для обычных offline tests.

## Этап 2 — write и webhooks (реализованы offline)

1. Invoice create/delete и payment address; клиентские условия priceAmount/minPayment.
2. Cheques и webhook verification Current v1: raw bytes, HMAC, compare_digest,
   timestamp в ms, configurable replay window. Unknown events сохраняются,
   повторная доставка и out-of-order события документируются.
3. Payouts, mass payouts (partial success), withdrawals, withdrawal links.
4. Контракт идемпотентности, поведение duplicate client ID и timeout после commit
   проверяются на testnet до автоматических повторов записей.

Все 25 Current REST операций реализованы после P015; write-методы покрыты
offline MockTransport. `tests/test_withdrawal_links.py` отдельно проверяет singular
POST/exact200, точные деньги, DTO bounds, optional links/unknown fields и ошибки
в sync/async. Наличие ссылки не требует перехода по ней.
Денежные end-to-end tests требуют отдельного явного задания и входных данных;
текущий проект таких тестов не содержит.

Webhook tests: `tests/test_webhook_signatures.py` проверяет Current raw-byte HMAC,
headers/time policy и diagnostics; `tests/test_webhook_events.py` — auth-first,
typed variants/unknown fallback, Decimal/aware dates, raw snapshots и девять known
nested date paths после correction. Reachable graph — **24 unique schemas** по
[accepted P017 review](../workflow/reviews/P017-02.md); прежний handoff count26
остаётся историей. Это не live signing/delivery/rotation/retry evidence.

`tests/test_examples.py` исполняет [read](../examples/pay_read.py),
[write](../examples/pay_write.py) и [webhook](../examples/pay_webhook.py) функции:
MockTransport, synthetic env/signing, testnet, exact money, stable ID, один вызов,
timeout, unknown status/fallback/finality и imports без credentials. Реальные
HTTP transports заблокированы fixture; top-level I/O в примерах нет. Эти cases
проверяют документацию как пользовательский сценарий и входят в full suite.

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

Harness содержит 40 cases для sync/async: 6 public (currencies/rates/health)
и 34 private, покрывающие все 15 GET. Hardcoded environment — testnet;
mainnet, POST/PUT/DELETE и получение токена в него не входят.

Gate проверяется во время fixture setup: только точное `XROCKET_RUN_LIVE=1`
разрешает запросы. Обычный pytest остаётся offline через `-m 'not live'`, даже
если флаг уже установлен. Явный `-m live` без флага даёт 40 skips до создания клиентов.

Private клиент использует только `XROCKET_PAY_TESTNET_TOKEN`, без fallback на
другие токены или автоматического чтения .env. Отсутствие JWT даёт 34 понятных skips,
публичные проверки продолжаются без токена. С одним JWT отдельно доступны
app.info/balances и list invoices/cheques/payouts/withdrawals (12 cases).

Каждый retrieve/payment проверяется отдельно по server/client ID из fixtures:

| Ресурс | Server ID variable | Client ID variable |
|---|---|---|
| Invoice retrieve и payments | `XROCKET_PAY_TESTNET_INVOICE_ID` | `XROCKET_PAY_TESTNET_CLIENT_INVOICE_ID` |
| Cheque | `XROCKET_PAY_TESTNET_CHEQUE_ID` | `XROCKET_PAY_TESTNET_CLIENT_CHEQUE_ID` |
| Payout | `XROCKET_PAY_TESTNET_PAYOUT_ID` | `XROCKET_PAY_TESTNET_CLIENT_PAYOUT_ID` |
| Withdrawal | `XROCKET_PAY_TESTNET_WITHDRAWAL_ID` | `XROCKET_PAY_TESTNET_CLIENT_WITHDRAWAL_ID` |

Отсутствующий ID пропускает только соответствующий case; независимые app/list
не зависят от fixtures. ID не угадываются и не извлекаются из list response.
Quotas (2 cases) требуют оба `XROCKET_PAY_TESTNET_QUOTAS_NETWORK` и
`XROCKET_PAY_TESTNET_QUOTAS_ASSET`; неполная пара пропускает только quotas.
Непустой, но некорректный fixture приводит к failure, а не skip.

Приватные setup/GET/cleanup failures дают постоянное сообщение без traceback
с records, ID, JWT или problem body. Request logs на время live tests отключены
и затем восстановлены; ответы в fixtures не записываются. Недоступность сети,
HTTP error или некорректный response при opt-in — failure, не skip/xfail/pass.

На Windows при исчерпании локальных socketpair (WinError 10055) отдельный запуск:

```powershell
.venv\Scripts\python.exe -m pytest -m live -o asyncio_default_test_loop_scope=session
```

`tests/test_live_harness.py` проверяет gates, independent skips, testnet GET-only,
failure semantics и отсутствие чувствительных synthetic значений в выводе
через отдельные pytest processes с подставленным HTTPX send. Это offline
проверка harness, не live подтверждение API. Реальные результаты и открытые
вопросы сохраняются в [журнале live](live-verification.md); первый срез
[verification.md](verification.md) остаётся историческим.
