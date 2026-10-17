# BASE: Исходный срез: шесть GET-операций Current Pay

## Цель
Сохранить проверяемую точку отсчёта SDK перед расширением ресурсов.

## Прочитать
- `AGENTS.md` — общий протокол одной сессии; статусы берутся из `workflow/tasks.json`.
- `README.md`, `spec/architecture.md`, `spec/pay-api.md`.
- `spec/verification.md`, `workflow/handoffs/BASE-01.md`.
- `src/xrocket/_core/transport.py`, `src/xrocket/pay/`, `tests/`.

## Входит
- Sync/async: app.info, app.balances, currencies.list, rates.get, invoices.list/retrieve.
- Типизированные ответы, Decimal, одна cursor-страница, HTTP errors и lifecycle.
- Историческая проверка: 156 offline tests и два публичных testnet smoke.

## Не входит
- Остальные 19 операций, запись, webhook verification, Legacy и Exchange.

## Приёмка
- Шесть wire method/path соответствуют inventory в tasks.json.
- Публичные импорты и исторические ограничения описаны в README и handoff.
- Результаты 17.10.2026 остаются историческими; новые проверки указывают новую дату.

## Проверка
- Существующие `tests/test_contracts.py`, `tests/test_models.py`, `tests/test_transport.py`.
- При необходимости перепроверки: `.venv\Scripts\python.exe -m pytest tests/test_contracts.py tests/test_models.py tests/test_transport.py`.
- Не повторять исходное исследование ради старта следующей карточки.

## Источники
- `spec/openapi/pay-current.json`: шесть GET из inventory; `spec/verification.md`.
