# Pay readiness ledger — 2026-10-18

P018, Asia/Tashkent. Входная база:
`a39b471abba804214716917eb91d7e17fe140ed2`, чистое дерево, все прямые зависимости
done. Scope — завершить проверку сохранённого Current Pay контракта; X001 не начата.
Итоговый handoff: [P018-01](../workflow/handoffs/P018-01.md).

## Решение и источники

Pay имеет полный **offline** scope: 18 paths / 25 REST operations, ровно один
queue owner каждой операции, 25 sync и 25 async public methods. Матрица
[operation → API → tests/source](pay-operation-matrix.md) содержит verb/path,
auth, query/body, response/status/error policies и конкретные fixture/test anchors.
Проверены реальные вызовы и test bodies; `tools/session.py check` отдельно
доказывает только плановое покрытие очереди. Эти два доказательства не смешиваются.

Источник — snapshot [Current OAS](openapi/pay-current.json), API version1.0.0,
полученный 2026-10-17, SHA256
`6061070427088b6775ad2065f9be01a0da1c64780de34cb63e6196bde5ad3241`.
[Manifest](openapi/manifest.json) и оба snapshots сохранены без правок. Источники
официального API перечислены в [Pay spec](pay-api.md#1-источники-и-приоритет);
в P018 сеть и актуальная документация сервера не запрашивались.

Это достаточная граница для отдельного исследования Exchange, не production
certification Pay и не подтверждение end-to-end денежных сценариев. Exchange
по-прежнему reserved namespace. Совместимость с будущим Exchange API/runtime
до его исследования не утверждается; X001 должна сначала зафиксировать его
источники/auth/REST/WS/pagination и собственные DTO, сохраняя Pay imports/behavior.

## Новый offline проход P018

Среда: Windows 11 10.0.26200, x64; CPython3.12.14 (MSC1944).
HTTPX0.28.1, Pydantic2.14.1, pytest9.1.1, pytest-asyncio1.4.0, Ruff0.17.1,
mypy1.20.2, Hatchling1.32.4, build1.6.1. Все команды из корня SDK с его `.venv`.
Strict mypy использует обычный ignored `.mypy_cache`, не NUL.

| Команда / проверка | Новый результат | Граница |
|---|---|---|
| `.venv/Scripts/python.exe -m pytest tests/test_examples.py -q -o asyncio_default_test_loop_scope=session` | **9 passed** (внутренний helper) | Исполнение настоящих read/write/webhook examples, synthetic env/HMAC, MockTransport, сеть заблокирована fixture |
| `.venv/Scripts/python.exe -m pytest -o asyncio_default_test_loop_scope=session` | **3163 passed, 40 deselected**, 10.88s | Один новый полный offline запуск после финальных example/test правок; live marker исключён |
| `.venv/Scripts/python.exe -m ruff check .` | **All checks passed** | Source, tests, examples, tools |
| `.venv/Scripts/python.exe -m mypy` | **Success, 39 source files**, strict | Настроенный runtime scope `src`; examples выполняются отдельно, не включены в этот mypy count |
| `.venv/Scripts/python.exe -m build --no-isolation` | **Wheel/sdist built** | Runtime и examples упакованы; artifacts обновлены после docs/workflow edits для точного совпадения с итоговыми документами |
| `.venv/Scripts/python.exe -I .tmp/p018-wheel-smoke.py` | **PASS** после исправления helper preflight | 39 wheel Python files + py.typed byte-match source; 82 required sdist runtime/test/spec/example/docs files; ZIP-only imports, read/write sync/async и synthetic webhook/boundary checks |
| Offline OAS/queue/runtime/test introspection | **PASS** | 18 paths/25 operations, 25 unique owners, 50 methods/signatures/literal routes; named tests/fixtures реально существуют |
| AST product boundaries и public export identity | **PASS**, внутренний read-only helper | Core не импортирует продукты, Pay не импортирует Exchange; 62 model exports, из них 61 общие с Pay + models-only Money |
| `.venv/Scripts/python.exe tools/session.py check` | **PASS**, Ready X001 | 24 tasks,23 done/1todo; плановое покрытие25 операций, не runtime proof |
| Local Markdown links/heading anchors, `git diff --check` | **PASS**, 215 local targets | Файлы/anchors изменённых docs/workflow существуют, whitespace errors нет |

9 example cases входят в 3163 и не прибавляются к full total. Targeted/full
результаты P017 и независимого review — исторические, не добавляются к P018.
Windows session-loop workaround задан только CLI, permanent pytest config не менялся.
Новый runtime SDK код не менялся; документация теперь отражает реальную поверхность.
Внутренние helpers — части worker self-review, не отдельное acceptance review
координатора нового candidate SHA.

Первый smoke остановился на preflight assertion: `-I` всё ещё обрабатывает
editable-install `.pth`, добавивший `src` в sys.path. До SDK smoke дело не дошло.
Исправлен только ignored helper: пути checkout явно убраны, каждый загруженный
`xrocket` module обязан иметь origin внутри wheel ZIP. Повторный свежий smoke
прошёл. Это ошибка изоляции probe, не скрытый runtime defect. После финальных
docs/workflow изменений build/smoke обновлены для проверки точного sdist
с итоговыми документами; SDK tests повторять без code/test изменений не требуется.

## Что фактически подтверждено offline

- Все 15 GET и 10 mutations доступны у обоих клиентов. Singular/plural paths,
  алиасы, repeated query keys, URL encoding, filters/IDs/bounds проверены с
  синтетическими данными. Invoice payment-address — exact201, остальные writes
  exact200, DELETE body строго пустой. GET сохраняет историческую all2xx policy
  с DTO decoding, хотя OAS перечисляет только200 (D020).
- Отдельные strict request DTO, aliases/omission/null, recursive revalidation,
  exact Decimal → string, Unicode/password masking; response DTO не становятся
  request автоматически. Деньги/precision/optional total/null tolerance — явно
  описанные reader policies, не дополнительные серверные гарантии.
- Shared HTTP errors и endpoint-specific cases из матрицы сохраняют status,
  object problem и optional request-id/retry-after; все inline business problem
  subtypes OAS отдельными live fixtures не проверялись. Core transport исключения
  подавляют автоматическую печать исходного context, но он доступен явно.
- HTTP pooling и lifecycle, SDK-owned/injected ownership, timeout30/override,
  auth isolation, отсутствие SDK retries/redirects/auto-pagination/lookup,
  batch splitting и переходов по ссылкам. Внешний transport может иметь свои
  политики; SDK не обещает отменить их внутреннюю работу.
- Current webhook HMAC по исходным bytes до UTF-8/JSON/DTO, direct secret отдельно
  от JWT, typed variants и explicit unknown fallback. Finality только finalized_at,
  неизвестные статусы не означают paid. Девять известных вложенных date paths
  отвергают numeric epoch coercion. Проверена raw/diagnostic граница, а не реальная
  доставка или persistent replay storage.
- P017 correction принята по [review P017-02](../workflow/reviews/P017-02.md).
  Уточнённый reachable graph — **24 unique schemas**, все девять known date paths
  покрыты; прежние rejected round и count26 в handoff не переписаны.
- Pay/core/Exchange imports изолированы. Старые public imports сохранены,
  sync/async сигнатуры симметричны. Wheel и sdist проверяются отдельным smoke,
  включая py.typed; examples/spec/tests входят только в source distribution.

## Исторические live evidence — отдельный слой

Это пересказ сохранённых наблюдений, **в P018 live API не запускался**.
Подробности: [первый срез 2026-10-17](verification.md),
[журнал P007/P019](live-verification.md),
[P007 handoff](../workflow/handoffs/P007-01.md),
[P019 handoff](../workflow/handoffs/P019-01.md).

| Исторический запуск | Факт и практический предел |
|---|---|
| BASE public testnet | 2 GET passed (currencies/rates), без JWT; это ранний read-only срез |
| P007 public testnet | currencies/rates sync/async: 4 passed; rates no-token и repeated assets подтверждены для записанного USD/BTC/ETH запроса |
| P007 health deviation | 2 ResponseValidationError; отдельный GET200 вернул только `{"status":"ok"}` вместо OAS required component collections (PAY-018) |
| P019 health fix | После omission override2 public sync/async health tests passed; full/null components shapes проверены offline, не live |
| P007 private | 34 skips: JWT/ID/quota fixtures отсутствовали, private GET не выполнялись; mock harness pass не заменяет это отсутствие |
| P018 | Новый offline pass; live GET не opt-in и не требовался для DoD. Реальные env values/secrets/user payload не искались и не читались |

Первоначальные network failures P007 внутри sandbox и health failure остаются
в истории; последующий pass не делает их прежним успехом. Исторические count totals
не суммируются и не объявляются количеством сегодняшних уникальных проверок.

## Неподтверждённые факты и release limits

Список PAY-001–018 и [открытые вопросы](pay-api.md#12-открытые-вопросы-до-расширения-sdk)
остаются частью контракта, не закрыты зелёным pytest. В частности:

- Private records, pending/finalized платежи и nullable overrides (PAY-003–005,
  optional cheque/payout/withdrawal поля); реальное отсутствие payment.id, total;
  numerical precision/rounding, limit defaults/ranges и 4KB payload size metric.
- Rates optional auth во всех окружениях и остальных запросах; repeated invoice
  ids, размер array query, остальные cursor/limit/total semantics. Исторический
  rates GET не подтверждает эти условия для всего API.
- Invoice open amount/ни одной суммы (PAY-008), реальный mass batch limit и target
  types/атомарность (PAY-009/010), withdrawal create150/retrieve100 и missing-ID/
  приоритет двух ID (PAY-016/017), expiry/platform withdrawal links.
- Client-ID deduplication scope/retention/duplicate/replay, исходы после timeout,
  settlement/finality server guarantees, rate limits и стабильность problem codes.
  Timeout/ResponseValidationError не доказывает отказ денежной записи; negative
  lookup не доказывает safe replay. Автоматического повторения нет.
- Live webhook signing/delivery/retry/rotation/clock-skew/order и интеграция с
  HTTP framework не запускались. Окно ±300000ms — SDK policy; dedupe только
  приложением по **верхнему delivery id**, вместе с durable business transaction.
  Explicit raw/dumps/nested DTO и third-party traceback locals могут раскрыть data.
- Live mutations (включая invoices/address/link), платежи/выводы, mainnet,
  Legacy и Exchange не проверены. PyPI/deploy/release/publication P018 не выполняет.
- Проверено только Windows/x64/Python3.12.14 с указанными версиями зависимостей.
  Python3.11, 3.13+ и прочие заявленные >=3.11 версии, Linux/macOS, другие
  архитектуры и весь разрешённый диапазон зависимостей не запускались.

Переход к X001 возможен после независимого review P018 и действий координатора.
Готовность этого offline среза не снимает перечисленных ограничений и не разрешает
денежные live проверки или публикацию пакета.
