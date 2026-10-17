# Текущее состояние SDK

Обновлено: 2026-10-18. Это краткий контекст; статусы и выбор следующей задачи —
только в [tasks.json](tasks.json), воспроизводимые результаты — в handoffs.

## Есть сейчас

- Python SDK `xrocket-sdk` 0.1.0.dev0, `src` layout, HTTPX/Pydantic, Python 3.11+.
- `PayClient` / `AsyncPayClient`: app, cheques, currencies, health, rates, invoices,
  payouts, withdrawals, withdrawal_links. Реализованы все 25 Current Pay REST операций:
  все 15 GET, invoice create/delete, создание payment address, cheque create/update/delete
  и создание одиночного payout/mass payouts/withdrawal/withdrawal link.
- `health.get()` публичен; invoices поддерживают list/retrieve/payments, cheques
  и payouts — list/retrieve, withdrawals — list/retrieve/quotas.
  Каждый list читает одну страницу. Invoice payments имеют typed transactions
  и явный unknown fallback. Полный контракт — в [spec/pay-api.md](../spec/pay-api.md).
  P019 исправила PAY-018: status-only health читается; отсутствующие component
  collections — None (unknown), переданные [] сохраняются, explicit null отвергается.
  Для roundtrip missing используйте `model_dump(exclude_unset=True)`.
- List dates требуют aware datetime, cursor opaque. У payouts/withdrawals limit
  целочисленный без диапазона (OAS не задаёт bounds); у cheques — 1–1000.
- Withdrawal.amount и quotas min/fee — Decimal, quotas precision — strict конечное
  int/float без integer coercion. Response withdrawal status optional, network/status
  принимают неизвестные строки с сохранением регистра. Quotas требуют network/asset.
- Общие HTTP/errors, Decimal, aware datetime, aliases, unknown fields/statuses,
  явные страницы, ownership сессий, изоляция auth, без retries и redirects.
- P008: внутренний core поддерживает GET/POST/PUT/DELETE через request с явными
  success_statuses и TypeAdapter/None (JSON/строго пустой ответ); прежний get API
  сохранён. RequestModel/RequestMoney/serialize_request отделены от response DTO,
  aliases/missing/null и точные деньги проверяются до I/O, также внутри Any.
  P009 использует этот фундамент для публичных invoice create/delete.
- `invoices.create(request=InvoiceCreateRequest(...))` возвращает Invoice на 200;
  отдельные typed Callback/URL/CustomerRequest, strict camelCase inputs, точные суммы,
  millisecond expires_in/0 и omission. Explicit None запрещён по non-nullable OAS.
  Both amounts отвергаются, neither allowed по schema (PAY-008 остаётся открытым).
  `delete(invoice_id=..., client_invoice_id=...)` возвращает None на пустой 200.
  Create client ID без OAS maxLength; DELETE IDs — непустые str 1–100.
- P010: `invoices.create_payment_address(request=InvoiceCreatePaymentAddressRequest(...),
  invoice_id=..., client_invoice_id=...)` возвращает InvoicePaymentAddress только
  на HTTP 201. IDs 1–100 остаются в query, pay_network — обязательный body enum.
  Response expires_at обязателен и aware (без nullable override PAY-003),
  min_amount — optional Decimal; explicit null отвергается. Unknown response
  networks/fields сохраняются, реальные адреса через API не создавались.
- P011: `cheques.create(request=ChequeCreateRequest(...))`,
  `update(request=ChequeUpdateRequest(...), cheque_id=..., client_cheque_id=...)`
  и `delete(cheque_id=..., client_cheque_id=...)` используют plural `/api/v1/cheques`.
  Create требует asset/точный amount, client ID max50; query IDs 1–100.
  Update разрешает только description: omission → {}, пустая строка очищает,
  explicit None запрещён. Create/update возвращают Cheque на 200, delete —
  None на строго пустой 200. Password — SecretStr, обычные dumps/repr маскируются,
  field/model validation inputs удаляются из structured errors; raw HTTP body
  доступен явно. Cheque response и прежние public imports сохранены.
  Исправление P011-02 отвергает surrogate code points в request строках/ключах
  до создания JSON, чтобы UnicodeEncodeError не сохранял wire password.
  Нормальный Unicode/astral symbols сохраняются точным UTF-8.
- Pay-модели разделены по реализованным ресурсам в `pay/models/`, с отдельными
  `_base` (response config/Money) и pagination. Прежние public imports
  из `xrocket.pay.models` и `xrocket.pay` сохранены.
- P012: `payouts.create(request=PayoutCreateRequest(...))` возвращает существующий
  Payout только на 200. Required target/max100, target_type enum, asset и точный
  amount; optional client ID/max50, description без schema max и отдельный
  PayoutCallbackRequest (URL/max500, payload object). Omission сохраняется,
  explicit None запрещён. Client ID не генерируется и не меняется, duplicate
  API error не скрывается. Timeout оставляет неизвестный итог после одной HTTP
  попытки без lookup/retry; ручной retrieve по сохранённому client ID документирован.
- P013: `payouts.create_mass(request=MassPayoutCreateRequest(...))` делает один POST
  и на 200 возвращает `MassPayoutResult` с отдельными обязательными success_payouts
  (`Payout`) / error_payouts (`MassPayoutError` с typed reason), has_errors/is_partial.
  Batch asset не дублируется в item; request target_type только telegram_user_id
  по prose/summary при противоречивом OAS enum (PAY-010). Лимит500/непустота
  не выводятся из ошибочного object maxLength (PAY-009). IDs, порядок/дубликаты
  ответа сохраняются без позиционного matching или генерации/подстановки IDs.
  Нет splitting/fan-out/retry/replay; timeout оставляет исход items неизвестным.
- P014: `withdrawals.create(request=WithdrawalCreateRequest(...))` делает один POST
  и возвращает существующий Withdrawal только на 200. Client ID required/max150,
  caller-owned без генерации/замены/усечения; retrieve отдельно требует 1–100
  (PAY-016/017). Network enum задаётся явно, address100/comment50/callback URL500
  соответствуют schema. Деньги точные, address/asset/comment не нормализуются.
  Omission/null различаются; timeout оставляет неизвестный итог после одной
  HTTP попытки без retry/lookup/polling, lookup длинного ID не обещается.
- Current и Legacy OAS с checksum, архитектура, сравнение SDK и контракт Pay.
- P015: отдельный `withdrawal_links.create(request=WithdrawalLinkRequest(...))`
  использует singular POST/exact200. `WithdrawalLink` допускает отсутствие всех
  трёх ссылок; missing → None, present non-null string, без URL validation,
  unknown response fields сохраняются. Address100/comment50, required network,
  точный amount, optional platform только по указанию xRocket; нет ID/callback.
  SDK возвращает ссылки без открытия, timeout оставляет неизвестный итог одной попытки.
- P016: `verify_webhook_signature(raw_body=..., headers=..., webhook_secret=...)`
  в `xrocket.pay` — stateless Current HMAC-SHA256 по точным timestamp/body bytes,
  direct secret отдельно от JWT, v1 и constant-time comparison. Никакого JSON
  parsing/Legacy transform. Default окно ±300000 ms inclusive — SDK policy,
  настраивается tolerance_ms/целыми тестовыми clock ms; отдельные WebhookError
  subclasses не сохраняют входные значения/внутренние или caller cause/context.
  Повторную delivery внутри окна verifier примет; dedupe остаётся приложению.
- `xrocket.exchange` содержит только зарезервированный namespace.
- Система сессий: карточки, очередь, промпты, handoffs и read-only helper.
- Управляемый цикл: текущий чат-координатор, отдельные workers/reviewers, 5 минут,
  automatic commit/push после tests и принятого review. Scope P010–P018/X001.
  [Протокол](AUTOPILOT.md), [настройка](handoffs/AUTO001-01.md); текущая фаза и
  thread IDs — в ignored `workflow/.autopilot/state.json`. Параллельный ручной
  writer в этом checkout при активном worker не запускается.

## Подтверждённая база

Первый срез BASE: 156 offline tests; 2 public testnet GET tests; Ruff, strict
mypy (13 source files), wheel/sdist и editable install прошли на Windows/Python
3.12.14. Это **исторический результат**, не автоматическая гарантия текущего кода.
См. [BASE handoff](handoffs/BASE-01.md) и [spec/verification.md](../spec/verification.md).
Проверки самой системы сессий — в [FLOW handoff](handoffs/FLOW-01.md).

P001 (структура моделей) и P002 (health) завершены; их отдельные результаты —
в [P001 handoff](handoffs/P001-01.md) и [P002 handoff](handoffs/P002-01.md).
Другие завершённые read-задачи: [P003](handoffs/P003-01.md),
[P004](handoffs/P004-01.md), [P005](handoffs/P005-01.md). Их результаты исторические;
nullable overrides платежей, cheque/payout records подтверждены только synthetic fixtures.

Результаты P006/P007 — в [P006 handoff](handoffs/P006-01.md) и
[P007 handoff](handoffs/P007-01.md). На Windows обычный full pytest ранее давал
setup WinError 10055; рабочий override — `-o asyncio_default_test_loop_scope=session`.
Постоянный loop scope не менялся.

Live P007: public currencies/rates подтверждены sync/async (4 passed),
health — 2 ResponseValidationError. Отдельный GET подтвердил HTTP 200
`{"status":"ok"}` без обязательных по OAS info/error/details. Private — 34 skips,
JWT/ID/quota fixtures отсутствуют. См. [журнал](../spec/live-verification.md) и
[P007 handoff](handoffs/P007-01.md); private подтверждения не подменены mock pass.

Задача [P019](handoffs/P019-01.md): 53 целевых и 907 full offline tests
с указанным override прошли (40 live deselected). Ruff, strict mypy (28 files),
wheel/sdist и wheel-only Health smoke прошли. Повторный public testnet health
sync/async — 2 passed; исходный failure P007 сохранён в журнале как история.

Задача [P008](handoffs/P008-01.md): 460 целевых и 1221 full offline tests
с session-loop override прошли (40 live deselected); Ruff, strict mypy (29 files),
wheel/sdist и wheel-only sync/async mock writes прошли. Live не запускался,
исторические health/testnet результаты не подменены новым mock pass.

Задача [P009](handoffs/P009-01.md): 365 целевых и 1480 full offline tests,
Ruff, strict mypy (30 files), wheel/sdist и wheel-only sync/async invoice mock writes
прошли с session-loop override (40 live deselected). Исправлен serializer edge case:
required поля не теряются из-за вручную пустого fields_set; исходные DTO не меняются.
Live invoice mutations не выполнялись.

Задача [P010](handoffs/P010-01.md): 180 целевых и 1660 full offline tests
прошли с session-loop override (40 live deselected), Ruff и strict mypy (30 files)
прошли. Wheel/sdist и wheel-only sync/async payment address smoke прошли.
Независимое review принято: [P010-01](reviews/P010-01.md); координатор опубликовал
результат до начала P011. Live address creation не выполнялся.

Первый candidate P011 получил changes_requested: [P011-01 review](reviews/P011-01.md)
обнаружил утечку password через UnicodeEncodeError при surrogate input;
прежние 744/1955 passing tests этот случай не покрывали.
Исправление [P011-02](handoffs/P011-02.md): 771 целевой (cheque reads/writes +
request serialization/write transport) и 1982 full offline tests прошли
с session-loop override (40 live deselected). Ruff, strict mypy (31 files),
wheel/sdist и wheel-only sync/async cheque/Unicode smoke прошли. Локальный commit —
кандидат для отдельного review координатора; push/live mutations worker не выполняет.

P011 correction затем принята и опубликована координатором до P012;
evidence — [P011-02 review](reviews/P011-02.md).

Задача [P012](handoffs/P012-01.md): 277 целевых и 2120 full offline tests прошли
с session-loop override (40 live deselected); Ruff, strict mypy (32 files),
wheel/sdist и wheel-only sync/async payout create smoke прошли. Timeout/duplicate
проверены без скрытого второго запроса; ручной lookup тестируется отдельно.
Локальный commit — candidate для независимого review координатора;
push/live выплаты worker не выполняет.

P012 затем принята и опубликована координатором до начала P013;
evidence — [P012-01 review](reviews/P012-01.md).

Задача [P013](handoffs/P013-01.md): 175 целевых и 2295 full offline tests прошли
с session-loop override (40 live deselected); Ruff, strict mypy (33 files),
wheel/sdist и wheel-only sync/async mixed batch smoke прошли. Проверены три
варианта результата, точная wire serialization, исходные IDs/дубликаты,
отсутствие придуманного limit500 и ровно один HTTP attempt без retry/replay.
Локальный commit — candidate для независимого review координатора;
push/live batch выплаты worker не выполняет.

P013 затем принята и опубликована координатором до начала P014;
evidence — [P013-01 review](reviews/P013-01.md).

Задача [P014](handoffs/P014-01.md): 414 целевых и 2474 full offline tests прошли
с session-loop override (40 live deselected); Ruff, strict mypy (34 files),
wheel/sdist и wheel-only sync/async withdrawal create smoke прошли. Проверены
ID150/GET100 без усечения, деньги/Unicode и timeout с ровно одним POST.
Локальный commit — candidate для независимого review координатора;
push/live выводы worker не выполняет.

P014 затем принята и опубликована координатором до начала P015;
evidence — [P014-01 review](reviews/P014-01.md).

Задача [P015](handoffs/P015-01.md): 178 целевых и 2652 full offline tests прошли
с session-loop override (40 live deselected); Ruff, strict mypy (36 files),
wheel/sdist и wheel-only sync/async link smoke прошли. Проверены независимый
omission ссылок, explicit-null string policy, точная сумма, ограничения DTO,
ошибки и один POST без followup/retry. Локальный commit — candidate для
независимого review координатора; worker не выполнял push/live API/переходы по ссылкам.

P015 затем принята и опубликована координатором до начала P016;
evidence — [P015-01 review](reviews/P015-01.md).

Задача [P016](handoffs/P016-01.md): 146 целевых и 2798 full offline tests прошли
с session-loop override (40 live deselected); Ruff, strict mypy (38 files),
wheel/sdist и wheel-only signing/import smoke прошли. Три независимых known-answer
вектора, raw Unicode/whitespace, malformed headers, time boundaries и redaction
проверены синтетически. Локальный commit — candidate для независимого review
координатора; worker не выполнял push/live API и не использовал реальные secrets.

## Ограничения и ближайшее направление

Pay: webhook verification реализована offline; typed events остаются P017.
REST операции покрыты offline. Live webhook delivery/signing/retries/clock skew
не подтверждены; window policy не является upstream гарантией.
PAY-008: server acceptance invoice без сумм/open amount не подтверждён, monetary
bounds не угаданы. Integer num_payments/expires_in — SDK policy при OAS number;
prose4KB data/payload limit без определённой size metric оставлен серверу.
PAY-017 остаётся открытым: отсутствие обоих withdrawal IDs отвергает только
локальный SDK guard, missing-ID ответ/приоритет двух ID сервером не подтверждены.
PAY-016: create clientWithdrawalId допускает 150, GET — 100; общего maxLength нет.
Есть opt-in harness для всех 15 GET (40 sync/async cases). Private live requests
не выполнялись: testnet JWT отсутствует; независимые skips по отсутствующим ID
и quota pair проверены offline. Только `XROCKET_PAY_TESTNET_TOKEN`, без fallback.
Денежных live операций, production проверки, PyPI публикации не было.
Основной план: небольшие ресурсные задачи Pay, затем Exchange discovery.
Архитектура остаётся draft, но существующий public API сохраняется при расширении.

Transport поддерживает GET/POST/PUT/DELETE под `/api/`; точный `/health` — только GET,
без query/fragment в path. GET body не поддержан, mutations не повторяются.
PAY-009/010 остаются открыты: server batch limit/empty acceptance, остальные
batch target types, атомарность и deduplication/replay semantics live не подтверждены.
Следующая доступная задача — P017 (typed webhook events и unknown fallback);
она не начата. Продолжение — через `tools/session.py next`,
чтение её карточки и handoffs прямых зависимостей по обычному протоколу.
P019 завершена и включена в зависимости финальной P018.
Write foundation P008 завершён до write ресурсов. Новые API детали
исследуются в соответствующей карточке, а не угадываются на весь roadmap.

Git инициализирован в корне SDK, ветка `main`, origin:
`https://github.com/attikusfinch/xRocket-SDK.git`. После явного подтверждения
пользователя проект опубликован, `main` отслеживает `origin/main`; GIT001 завершена.
Исходный commit — `ba8350d`; подтверждения подключения и публикации —
в [GIT001 handoff](handoffs/GIT001-03.md). Локальные окружения, кэши,
сборки и секреты исключены; specs, lock и workflow сохраняются в Git.
Рабочая `.venv` — в SDK; если её нет, см. установку в [README](../README.md).
Нет необходимости читать прежние чаты или ставить плагины.

## После следующей сессии

Обнови этот краткий снимок фактическими возможностями/ограничениями. Не копируй
сюда весь отчёт и тестовую матрицу; дай ссылку на новый handoff. Не меняй исторические
числа первого среза так, будто они описывают новый результат.
