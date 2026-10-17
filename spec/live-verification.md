# Журнал read-only testnet проверок

P007, 2026-10-17. Это журнал конкретных наблюдений, не гарантия production API.
Исторический первый срез остаётся в [verification.md](verification.md).
Команды и variables описаны в [test-plan.md](test-plan.md).

## Выполнено

Harness содержит 40 live cases: 6 public и 34 private для обоих клиентов.
Флаг `XROCKET_RUN_LIVE=1` включался явно; environment жёстко testnet.
JWT, все ID fixtures и quota network/asset отсутствовали (проверено только
наличие variables, значения не выводились). Private GET не выполнялись.

| Проверка | Результат | Граница подтверждения |
|---|---|---|
| Currencies sync/async без JWT | 2 passed | Testnet GET, типизированные валюты; точные значения не фиксируются |
| Rates sync/async без JWT, base USD, assets BTC/ETH | 2 passed | Testnet optional auth, repeated assets keys, положительные конечные rates |
| Health sync/async без JWT | 2 failed: ResponseValidationError | Сервер ответил, текущий decoder несовместим; failure не превращён в skip |
| Private app/list/retrieve/payments/quotas | 34 skipped | Нет `XROCKET_PAY_TESTNET_TOKEN`; ни один private response не подтверждён |
| Дополнительный публичный health shape probe | HTTP 200, `{"status":"ok"}` | 2026-10-17 16:28:55 UTC; других JSON полей нет, PAY-018 |

Первый запуск внутри sandbox получил 6 TransportError и 34 skips из-за
сетевого ограничения. Повторный публичный прогон вне ограничения получил
4 passed и 2 health failures. Он также дал два предупреждения о недоступной
pytest cache (разные пользователи sandbox/host); результаты тестов от cache
не зависят. Дополнительный probe был только GET `/health` без auth.

## Подтверждённая несовместимость

OAS health требует status/info/error/details. Реальный testnet вернул только
status. P002 decoder требует все четыре поля, поэтому обе версии `health.get()`
отвергают payload. Snapshot и runtime в P007 не менялись; добавлены PAY-018
и карточка [P019](../workflow/tasks/P019.md) для совместимой модели и regression tests.
Public smoke остаётся красным до исправления. P007 завершает harness и журнал,
а не заявляет успешность всех 15 живых GET.

## Не подтверждено

- Private GET, nullable invoice/payment/transaction поля и реальные records.
- Encoding invoice ids, live cursor/total/limit/precision semantics и quotas.
- PAY-016/017, включая withdrawal missing-ID response и приоритет двух ID.
- Mainnet, write, денежные операции, webhooks, Legacy, Exchange.

Offline harness tests используют только synthetic payloads и fake env values.
Их pass доказывает gates/requests/skips/failures и privacy вывода, но не upstream
контракт. Реальные token/ID/записи, заголовки и body аккаунта не сохранялись.
Для новых подтверждений дописывать датированные наблюдения, не переписывать
исторический первый срез и не подменять skips mock-успехом.

## P019: повторная проверка health после исправления

2026-10-17. SDK поддерживает status-only response и полный OAS response.
Отсутствующие info/error/details возвращаются как None (unknown); явно переданные
пустые массивы остаются [], explicit null отвергается. Отсутствующая error collection
сама по себе не подтверждает отсутствие component errors.

Отдельный запуск вне сетевого ограничения sandbox, без JWT:

```powershell
$env:XROCKET_RUN_LIVE = '1'
.venv\Scripts\python.exe -m pytest tests/integration/test_public_live.py -m live -k health -o asyncio_default_test_loop_scope=session -p no:cacheprovider --tb=short -ra
```

Результат: **2 passed, 4 deselected**, sync/async `health.get()` успешно прочитали
живой ответ. Остальные четыре public cases не перезапускались; их подтверждение
сохраняется из P007. Private GET/credentials/records не использовались.

Offline: 45 health regression cases и 8 harness scenarios (53 целевых),
907 full tests, Ruff, strict mypy (28 runtime files), build и wheel-only imports
прошли. Полный OAS shape, malformed components и explicit null проверены offline,
а не объявлены новым live подтверждением.

PAY-018 обработан override в SDK; расхождение опубликованной OAS с наблюдением
P007 сохраняется. Первоначальные 2 health failures выше остаются историей,
актуальный health smoke после P019 зелёный. См. [handoff P019](../workflow/handoffs/P019-01.md).
