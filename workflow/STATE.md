# Текущее состояние SDK

Обновлено: 2026-10-17. Это краткий контекст; статусы и выбор следующей задачи —
только в [tasks.json](tasks.json), воспроизводимые результаты — в handoffs.

## Есть сейчас

- Python SDK `xrocket-sdk` 0.1.0.dev0, `src` layout, HTTPX/Pydantic, Python 3.11+.
- `PayClient` / `AsyncPayClient`, ресурсы app, currencies, rates, invoices.
- Реализованы 6 из 25 Current Pay операций: app-info, balances, currencies, rates,
  invoices list и invoice retrieve (все GET). Точные paths — в карточке BASE.
- Общие HTTP/errors, Decimal, aware datetime, aliases, unknown fields/statuses,
  явные страницы, ownership сессий, изоляция auth, без retries и redirects.
- Pay-модели разделены на пакет `pay/models/`: app, currencies, rates, invoices,
  отдельные `_base` (response config/Money) и pagination. Прежние public imports
  из `xrocket.pay.models` и `xrocket.pay` сохранены.
- Current и Legacy OAS с checksum, архитектура, сравнение SDK и контракт Pay.
- `xrocket.exchange` содержит только зарезервированный namespace.
- Система сессий: карточки, очередь, промпты, handoffs и read-only helper.

## Подтверждённая база

В предыдущей сессии: 156 offline tests; 2 public testnet GET tests; Ruff, strict
mypy (13 source files), wheel/sdist и editable install прошли на Windows/Python
3.12.14. Это **исторический результат**, не автоматическая гарантия текущего кода.
См. [BASE handoff](handoffs/BASE-01.md) и [spec/verification.md](../spec/verification.md).
Проверки самой системы сессий — в [FLOW handoff](handoffs/FLOW-01.md).

P001 завершена: в её сессии прошли 170 offline tests, Ruff, strict mypy
(19 source files), build wheel/sdist и изолированный import smoke из wheel.
Live tests не запускались. Результаты и независимая самопроверка переноса —
в [P001 handoff](handoffs/P001-01.md).

## Ограничения и ближайшее направление

Pay: ещё нет write methods, остальных GET и webhook verification/typed events.
Приватные live tests не запускались: testnet JWT пользователь не предоставлял.
Денежных live операций, production проверки, PyPI публикации не было.
Основной план: небольшие ресурсные задачи Pay, затем Exchange discovery.
Архитектура остаётся draft, но существующий public API сохраняется при расширении.

Transport умеет только GET и разрешает paths только под `/api/`, а `/health`
расположен вне этого prefix. Следующая доступная задача — P002; она не начата.
Write foundation вынесен отдельной задачей до write ресурсов. Новые API детали
исследуются в соответствующей карточке, а не угадываются на весь roadmap.

Git инициализирован в корне SDK, ветка `main`, origin:
`https://github.com/attikusfinch/xRocket-SDK.git`. GIT001 сохраняет исходный проект
в репозитории; ход и подтверждения — в её handoff. Локальные окружения, кэши,
сборки и секреты исключены; specs, lock и workflow сохраняются в Git.
Рабочая `.venv` — в SDK; если её нет, см. установку в [README](../README.md).
Нет необходимости читать прежние чаты или ставить плагины.

## После следующей сессии

Обнови этот краткий снимок фактическими возможностями/ограничениями. Не копируй
сюда весь отчёт и тестовую матрицу; дай ссылку на новый handoff. Не меняй исторические
числа первого среза так, будто они описывают новый результат.
