# FLOW-01: система отдельных сессий SDK

Дата: 2026-10-17. Итог: done. Текущий статус хранится в tasks.json.

## Результат и файлы

Добавлены точки входа `F:/xrocket-pay/AGENTS.md`, SDK `AGENTS.md` и `START.md`.
В workspace сохранены переданные пользователем VPN-инструкции. Настройки Codex
за пределами проекта не менялись; новые чаты и automations не создавались.

`workflow/` содержит краткий STATE, DECISIONS, универсальные PROMPTS, templates,
21 карточку и tasks.json: BASE/FLOW, P001–P018, X001. Операции Pay распределены
по одному владельцу, статусы только в JSON. Завершение требует нового handoff и
обновления контекста. Read-only helper `tools/session.py` печатает next/ID/review
prompts и проверяет ссылки, зависимости, статусы, coverage исходной Pay OAS.
README ссылается на START. Runtime SDK и его tests не изменялись.
В `pyproject.toml` расширен состав sdist: START, AGENTS, workflow и helper также
попадут в исходный архив. Wheel по-прежнему содержит только исполняемый SDK.

## Решения

Одна карточка — один конечный результат с проверками и передачей. Незавершённая
работа продолжается под тем же ID. Агент не начинает вторую карточку автоматически.
Нет отдельного согласования каждой рутинной реализации. Запуск реальных финансовых
операций не следует из списка future write tasks. Обоснование AGENTS discovery
проверено по официальной OpenAI documentation, ссылка в START.md.

Очередь доводит Pay до полноты; Exchange сначала исследуется в X001. До исследования
его endpoint names не выдумываются. `operations` сейчас означает только Pay snapshot;
учёт Exchange endpoints и адаптация checker решаются в X001 на реальном контракте.

## Проверки

| Проверка | Результат текущей сессии |
|---|---|
| `.venv/Scripts/python.exe tools/session.py check` | Passed: 21 задача, 2 done / 19 todo, ready P001, все 25 Pay operations ровно по одному владельцу |
| `tools/session.py next` и `prompt P001` тем же Python | Passed: один и тот же P001, карточка, прямой handoff FLOW, протокол завершения |
| `tools/session.py review BASE` | Passed: отдельный read-only review prompt |
| Восемь невалидных очередей в памяти | Отвергнуты: duplicate/missing operation, cycle, unknown dependency, missing/wrong handoff, two active, premature start |
| Продолжение in_progress P001 без handoff, в памяти | Passed: выбирается тот же P001, не новая задача |
| Запрет prompt P018 до завершения зависимостей | Passed: exit 2 |
| SHA-256 workflow файлов до/после helper | Совпадают: команды read-only |
| `.venv/Scripts/python.exe -m ruff check .` | Passed |
| Локальные Markdown ссылки | Проверены 17 targets в 31 файле, все существуют |
| `.venv/Scripts/python.exe -m build --no-isolation` + просмотр архивов | Passed: sdist включает workflow/START/AGENTS/helper, wheel содержит только typed SDK |
| Независимый агент без истории чата | Определил P001, scope, проверки и завершение из файлов; найденные неверные пути PROMPTS и encoding исправлены |

Кириллица helper проверена после принудительного UTF-8 stdout/stderr. Прежние
156 offline/2 live SDK результата относятся к BASE и не заявляются новым запуском;
SDK runtime/tests не менялись, поэтому эти suites не повторялись.

## Продолжение

Следующий ID — P001: разделить response models по ресурсам с сохранением public
imports. P001 в этой сессии не выполнялся. Git не инициализирован, commit отсутствует.
Очередь — файловая договорённость, а не блокировка одновременных сессий.
