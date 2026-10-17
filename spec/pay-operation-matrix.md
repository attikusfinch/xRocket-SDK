# Pay Current: operation → API → evidence

Аудит P018 от **2026-10-18**. Это сверка сохранённого контракта и offline
реализации, а не новое обращение к API. Источник wire contract — неизменённый
[Current OAS](openapi/pay-current.json), загруженный 2026-10-17;
[provenance и hash](openapi/manifest.json), [приоритеты и overrides](pay-api.md).
В snapshot 18 path keys / 25 HTTP operations. Каждая строка ниже имеет ровно
одного владельца в [очереди](../workflow/tasks.json), один sync и один async
public method и конкретное синтетическое evidence в tests.

`tools/session.py check` сверяет **плановое** покрытие очереди с snapshot. Сам по
себе он не вызывает public API и не доказывает реализацию. Здесь дополнительно
прочитаны фактические resources/DTO/test bodies; существование обеих реализаций,
совпадение signatures и routes проверено отдельным offline introspection pass.
Результаты нового полного запуска pytest/Ruff/mypy/build и wheel smoke следует
читать в [P018 readiness ledger](pay-readiness-2026-10-18.md) и
[handoff](../workflow/handoffs/P018-01.md); эта матрица не подменяет их.

## Как читать контракт

В колонке API указан путь от `PayClient` и `AsyncPayClient`; async метод вызывается
через `await`. Обе resource implementations подключены в
[client.py](../src/xrocket/pay/client.py). Входные Python имена snake_case,
wire aliases camelCase. Пустой вход `—` означает отсутствие query/body.
`request=` — обязательный keyword-only DTO, передаваемый как JSON
`application/json`; raw dict и response DTO не заменяют request DTO.

Каждая строка задаёт точный OAS JSON pointer по правилу
`#/paths/<escaped path>/<lowercase verb>`, где `/` в path заменяется на `~1`.
Например, строка 25 —
`#/paths/~1api~1v1~1invoices~1payments~1address/post`.
Имя OAS DTO в колонке ответа/профиле входа — pointer
`#/components/schemas/<имя>`. Это позволяет проверить каждый request/response и
все inline error schemas непосредственно в snapshot, без narrative догадок.

Auth `JWT` означает Bearer token, обязательный **в SDK до I/O**. `Public`
разрешает отсутствие SDK token; явно переданный Pay token всё равно отправляется.
Defaults `Authorization`/auth внедрённой HTTPX session не заменяют SDK token.
Для rates это явный PAY-002 override: OAS security требует bearer, summary
обещает optional auth; исторический testnet no-token rates подтверждён только
для записанного запроса. Другие public операции не имеют OAS security.

В колонке success указан **OAS status**. GET сохраняет прежнюю SDK policy D020:
принимает любой 2xx, только если body декодируется ожидаемой моделью. Это шире
единственного OAS `200`; точный `200` для GET здесь не заявляется.
POST/PUT/DELETE принимают только указанный success status; DELETE требует ровно
пустые bytes (JSON, пробелы и другой 2xx отвергаются).

## 25 операций

Fixture names относятся к синтетическим constants/helpers внутри указанного
test file, не к записанным ответам аккаунта. Названные runtime tests используют
`httpx.MockTransport`, параметризованы на sync/async и проверяют вызов, а не
только наличие имени метода. Дальнейшие tests в том же файле уточняют границы;
основные anchors перечислены после таблицы.

| № / owner | Wire operation | Public API | Auth / вход | OAS success → Python | OAS error HTTP | Runtime evidence / fixture |
|---|---|---|---|---|---|---|
| 1 / P002 | `GET /health` | `health.get()` | Public / — | `200` inline object → `Health` | не перечислены | [test_health.py](../tests/test_health.py): `test_health_is_one_anonymous_request_at_the_origin_root`; `HEALTH`, omission cases |
| 2 / BASE | `GET /api/v1/app-info` | `app.info()` | JWT / — | `200 AppResponseDto` → `AppInfo` | 401, 500 | [test_contracts.py](../tests/test_contracts.py): `test_read_contracts[app.info]`; `CASES` app object |
| 3 / BASE | `GET /api/v1/balances` | `app.balances()` | JWT / — | `200 AppBalancesResponseDto` → `AppBalances` | 401, 500 | [test_contracts.py](../tests/test_contracts.py): `test_read_contracts[app.balances]`; `CASES` balances array/exact money |
| 4 / P009 | `POST /api/v1/invoices` | `invoices.create(request=...)` | JWT / B1 | `200 InvoiceDto` → `Invoice` | 400, 401, 404, 429, 500 | [test_invoices_write.py](../tests/test_invoices_write.py): `test_create_sends_every_documented_field_and_returns_typed_invoice`, `test_create_omission_and_explicit_values_keep_wire_semantics`; `INVOICE` |
| 5 / BASE | `GET /api/v1/invoices` | `invoices.list(...)` | JWT / Q1 | `200 InvoiceListResponseDto` → `CursorPage[Invoice]` | 401, 429, 500 | [test_contracts.py](../tests/test_contracts.py): `test_read_contracts[invoices.list]`, `test_empty_page_is_terminal_and_omitted_queries_are_absent`; `INVOICE`, page in `CASES` |
| 6 / BASE | `GET /api/v1/invoice` | `invoices.retrieve(...)` | JWT / ID-invoice | `200 InvoiceDto` → `Invoice` | 400, 401, 404, 429, 500 | [test_contracts.py](../tests/test_contracts.py): `test_read_contracts[invoices.retrieve]`, `test_retrieve_accepts_either_identifier`; `INVOICE` |
| 7 / P009 | `DELETE /api/v1/invoice` | `invoices.delete(...)` | JWT / ID-invoice; без body | `200` без schema → `None`, пустые bytes | 400, 401, 404, 429, 500 | [test_invoices_write.py](../tests/test_invoices_write.py): `test_delete_uses_singular_path_literal_identifiers_and_bodyless_200`, `test_delete_does_not_treat_json_or_whitespace_as_bodyless_success` |
| 8 / P003 | `GET /api/v1/invoice/payments` | `invoices.payments(...)` | JWT / ID-invoice + Q2 | `200 InvoicePaymentListResponseDto` → `InvoicePaymentPage` | 400, 401, 404, 429, 500 | [test_invoice_payments.py](../tests/test_invoice_payments.py): `test_payment_request_uses_current_route_and_exact_identifier_aliases`, `test_payment_response_decodes_each_transaction_and_preserves_future_fields`; `_payment`, `_transaction`, `_page` |
| 9 / P011 | `POST /api/v1/cheques` | `cheques.create(request=...)` | JWT / B3 | `200 ChequeResponseDto` → `Cheque` | 400, 401, 403, 404, 429, 500 | [test_cheques_write.py](../tests/test_cheques_write.py): `test_mutations_use_plural_routes_and_separate_query_from_body[create]`, `test_create_sends_every_documented_field_with_exact_amount_and_password`; `CHEQUE` |
| 10 / P004 | `GET /api/v1/cheques` | `cheques.list(...)` | JWT / Q3 | `200 ChequeListResponseDto` → `CursorPage[Cheque]` | 401, 429, 500 | [test_cheques_read.py](../tests/test_cheques_read.py): `test_cheque_routes_queries_and_minimal_response[list]`, `test_cheque_pagination_returns_one_page_without_following_next`; `_cheque`, `_page` |
| 11 / P011 | `PUT /api/v1/cheques` | `cheques.update(request=..., ...)` | JWT / ID-cheque + B4 | `200 ChequeResponseDto` → `Cheque` | 400, 401, 404, 429, 500 | [test_cheques_write.py](../tests/test_cheques_write.py): `test_mutations_use_plural_routes_and_separate_query_from_body[update]`; `CHEQUE` |
| 12 / P011 | `DELETE /api/v1/cheques` | `cheques.delete(...)` | JWT / ID-cheque; без body | `200` без schema → `None`, пустые bytes | 400, 401, 404, 429, 500 | [test_cheques_write.py](../tests/test_cheques_write.py): `test_mutations_use_plural_routes_and_separate_query_from_body[delete]`, `test_delete_requires_a_strictly_empty_200_body` |
| 13 / P004 | `GET /api/v1/cheque` | `cheques.retrieve(...)` | JWT / ID-cheque | `200 ChequeResponseDto` → `Cheque` | 400, 401, 404, 429, 500 | [test_cheques_read.py](../tests/test_cheques_read.py): `test_cheque_routes_queries_and_minimal_response[retrieve]`, `test_cheque_nested_response_preserves_unknown_state_and_fields`; `_cheque` |
| 14 / P012 | `POST /api/v1/payouts` | `payouts.create(request=...)` | JWT / B5 | `200 AppPayoutResponseDto` → `Payout` | 400, 401, 403, 404, 429, 500 | [test_payouts_write.py](../tests/test_payouts_write.py): `test_create_sends_one_post_with_exact_money_and_returns_open_response`; `REQUIRED`, `PAYOUT`, `_body` |
| 15 / P005 | `GET /api/v1/payouts` | `payouts.list(...)` | JWT / Q4 | `200 AppPayoutListResponseDto` → `CursorPage[Payout]` | 400, 401, 429, 500 | [test_payouts_read.py](../tests/test_payouts_read.py): `test_payout_routes_queries_and_minimal_response[list]`, `test_payout_pagination_returns_one_page_without_following_next`; `_payout`, `_page` |
| 16 / P005 | `GET /api/v1/payout` | `payouts.retrieve(...)` | JWT / ID-payout | `200 AppPayoutResponseDto` → `Payout` | 400, 401, 404, 429, 500 | [test_payouts_read.py](../tests/test_payouts_read.py): `test_payout_routes_queries_and_minimal_response[retrieve]`, `test_payout_nested_response_preserves_unknown_status_and_fields`; `_payout` |
| 17 / P014 | `POST /api/v1/withdrawals` | `withdrawals.create(request=...)` | JWT / B7 | `200 WithdrawalResponseDto` → `Withdrawal` | 400, 401, 403, 404, 429, 500 | [test_withdrawals_write.py](../tests/test_withdrawals_write.py): `test_create_sends_one_post_with_exact_money_and_open_withdrawal_response`; `REQUIRED`, `WITHDRAWAL`, `_body` |
| 18 / P006 | `GET /api/v1/withdrawals` | `withdrawals.list(...)` | JWT / Q5 | `200 WithdrawalListResponseDto` → `CursorPage[Withdrawal]` | 401, 429, 500 | [test_withdrawals_read.py](../tests/test_withdrawals_read.py): `test_withdrawal_routes_queries_and_minimal_response[list]`, `test_withdrawal_pagination_returns_one_page_without_following_next`; `_withdrawal`, `_page` |
| 19 / P006 | `GET /api/v1/withdrawal` | `withdrawals.retrieve(...)` | JWT / ID-withdrawal | `200 WithdrawalResponseDto` → `Withdrawal` | 401, 404, 429, 500 | [test_withdrawals_read.py](../tests/test_withdrawals_read.py): `test_withdrawal_routes_queries_and_minimal_response[retrieve]`; `_withdrawal` |
| 20 / P006 | `GET /api/v1/withdrawal-quotas` | `withdrawals.quotas(...)` | JWT / Q6 required | `200 WithdrawalQuotasResponseDto` → `WithdrawalQuotas` | 401, 429, 500 | [test_withdrawals_read.py](../tests/test_withdrawals_read.py): `test_withdrawal_routes_queries_and_minimal_response[quotas]`, `test_quotas_precision_preserves_json_number_type_and_extra_fields`; `_quotas` |
| 21 / P015 | `POST /api/v1/withdrawal-link` | `withdrawal_links.create(request=...)` | JWT / B8 | `200 WithdrawalLinkResponseDto` → `WithdrawalLink` | 400, 401, 404, 429, 500 | [test_withdrawal_links.py](../tests/test_withdrawal_links.py): `test_exact_post_body_and_optional_links_without_followup_requests`, `test_each_response_link_is_independently_optional`; `REQUIRED`, `LINKS`, `_body` |
| 22 / P013 | `POST /api/v1/mass-payouts` | `payouts.create_mass(request=...)` | JWT / B6 | `200 MassPayoutsCreateResponseDto` → `MassPayoutResult` | 400, 401, 403, 429, 500 | [test_mass_payouts.py](../tests/test_mass_payouts.py): `test_create_mass_sends_exact_batch_body_once`, `test_results_keep_reordered_original_item_ids_and_explicit_failures`; `ITEM`, `PAYOUT`, `REASON`, `ERROR`, `EMPTY_RESULT` |
| 23 / BASE | `GET /api/v1/currencies` | `currencies.list(...)` | Public / Q7 | `200 CurrencyResponseDto[]` → `list[Currency]` | 429, 500 | [test_contracts.py](../tests/test_contracts.py): `test_read_contracts[currencies.list]`; `CASES` currency/network array |
| 24 / BASE | `GET /api/v1/rates` | `rates.get(...)` | Public, PAY-002 / Q8 | `200 RateResponseDto[]` → `list[Rate]` | 404, 429, 500 | [test_contracts.py](../tests/test_contracts.py): `test_read_contracts[rates.get]`; `CASES` exact rate array; shared no-token/auth isolation tests |
| 25 / P010 | `POST /api/v1/invoices/payments/address` | `invoices.create_payment_address(request=..., ...)` | JWT / ID-invoice + B2 | **`201 InvoicePaymentAddressResponseDto`** → `InvoicePaymentAddress` | 400, 401, 403, 404, 429, 500 | [test_invoice_payment_addresses.py](../tests/test_invoice_payment_addresses.py): `test_create_sends_query_ids_and_network_body_and_decodes_exact_201`; `ADDRESS` |

Square-bracket labels above select a case conceptually; exact collected pytest
node IDs also contain sync/async and other parameter values.

## Вход: query и identifiers

Все перечисленные Q-поля optional, кроме обоих Q6. Неуказанные query fields
опускаются, empty string сохраняется, cursor не декодируется. Date filters
принимают aware `datetime` и сериализуются через `isoformat()` с offset.
У filter enum runtime guards есть в cheques/withdrawals; `currencies.kind`
ограничен type hint `Literal`, без отдельного runtime enum guard. Не следует
приписывать ему request DTO validation.

| Profile | Wire names / SDK policy | Реализация и дополнительное evidence |
|---|---|---|
| ID-invoice | `invoiceId`, `clientInvoiceId`; ≥1 непустой str 1–100; оба передаются, invoice priority заявлена upstream prose | [resources/invoices.py](../src/xrocket/pay/resources/invoices.py) `_retrieve_params`; `test_retrieve_accepts_either_identifier`, write/delete/payment-address identifier boundary tests |
| ID-cheque | `chequeId`, `clientChequeId`; ≥1 str 1–100; оба передаются без обещания приоритета | [resources/cheques.py](../src/xrocket/pay/resources/cheques.py) `_retrieve_params`; read routes/bounds, `test_invalid_identifiers_fail_before_network` |
| ID-payout | `payoutId`, `clientPayoutId`; ≥1 str 1–100; оба передаются без обещания приоритета | [resources/payouts.py](../src/xrocket/pay/resources/payouts.py) `_retrieve_params`; read routes/bounds and `test_invalid_payout_arguments_fail_before_network` |
| ID-withdrawal | `withdrawalId`, `clientWithdrawalId`; SDK требует ≥1 str 1–100; upstream missing-ID 400 и приоритет **не подтверждены** (PAY-017) | [resources/withdrawals.py](../src/xrocket/pay/resources/withdrawals.py) `_retrieve_params`; read route/bounds and `test_invalid_withdrawal_arguments_fail_before_network` |
| Q1 | `asset`, `fiat`, repeated `ids`, `status`, `cursor`, `limit`; limit strict int 1–1000 (OAS number/max1000; lower bound/integer — SDK policy) | [resources/invoices.py](../src/xrocket/pay/resources/invoices.py) `_list_params`; `test_read_contracts` asserts exact query key set, repeated IDs and opaque cursor |
| Q2 | `cursor`, `limit`; strict int 1–1000, без передачи чужого total | [resources/invoices.py](../src/xrocket/pay/resources/invoices.py) `_payments_params`; `test_payment_cursor_is_opaque_and_limit_boundaries_are_preserved`, `test_invalid_payment_arguments_fail_before_the_network` |
| Q3 | `fromDate`, `toDate`, `targetType`, `target`, `state`, `cursor`, `limit`; target/type парные, target≤100; targetType=user_id/telegram_user_id/telegram_username; state=active/completed/draft/error; limit int 1–1000 | [resources/cheques.py](../src/xrocket/pay/resources/cheques.py) `_list_params`; route cases cover enums, dates/offsets, empty target/cursor, limit boundaries; invalid inputs fail before I/O |
| Q4 | `fromDate`, `toDate`, `cursor`, `limit`; limit int без bool; диапазон/default не добавлены (OAS не задаёт min/max) | [resources/payouts.py](../src/xrocket/pay/resources/payouts.py) `_list_params`; routes include 0/negative/>1000 unchanged, aware dates and each ID |
| Q5 | `fromDate`, `toDate`, `status`, `cursor`, `limit`; status=CREATED/COMPLETED/FAIL, case-sensitive; limit как Q4 | [resources/withdrawals.py](../src/xrocket/pay/resources/withdrawals.py) `_list_params`; route/invalid tests distinguish request enum and open response status |
| Q6 | required `network`, `asset`; network=TON/BSC/ETH/BTC/TRX/SOL; asset str, empty допустим по schema | [resources/withdrawals.py](../src/xrocket/pay/resources/withdrawals.py) `_quotas_params`; all networks in routes; `test_quotas_query_arguments_are_required` |
| Q7 | `kind`: crypto/fiat, optional; SDK не подставляет default | [resources/currencies.py](../src/xrocket/pay/resources/currencies.py); `test_read_contracts`, public transport tests |
| Q8 | `base`, repeated `assets`; SDK не подставляет OAS default USD | [resources/rates.py](../src/xrocket/pay/resources/rates.py) `_params`; `test_read_contracts`; repeated keys — PAY-015, historical rates testnet evidence ограничено записанным запросом |

## Вход: JSON bodies

Для всех B-профилей: strict типы, extra forbidden, optional omission допустим,
explicit None отвергается (внутри custom JSON payload `null` допустим).
`RequestMoney` — finite `Decimal` или decimal string, сериализуется JSON string
без округления; float/int/bool не принимаются. DTO повторно валидируется перед
I/O, включая model_construct/mutation и вложенные объекты. Денежные min/max,
общая precision и format URLs/email/адресов не выдумываются.

| Profile / OAS DTO → Python request | Required / optional wire fields и ограничения | Код / regression evidence |
|---|---|---|
| B1 `InvoiceCreateRequestDto` → `InvoiceCreateRequest` | required `priceCurrency`; optional `priceAmount`, `minPayment` (не вместе; обе missing допустимы по schema, acceptance PAY-008 open), `numPayments` strict int 1–1000000, `payoutCurrency`, `payCurrencies`, `clientInvoiceId` (нет create maxLength), `description`≤1000, `expiresIn` strict int ms/0 сохраняется без подстановки default, `callback`, `url`, `customer`, `data`, `platformId` | [invoice_requests.py](../src/xrocket/pay/models/invoice_requests.py); `test_create_sends_every_documented_field_and_returns_typed_invoice`, omission/type/bounds/amount-conflict/bypass tests; `test_request_field_aliases_and_operation_policies_match_the_saved_snapshot` |
| B2 `InvoiceCreatePaymentAddressRequestDto` → `InvoiceCreatePaymentAddressRequest` | required `payNetwork`=TON/BSC/ETH/BTC/TRX/SOL; IDs только query | [invoice_requests.py](../src/xrocket/pay/models/invoice_requests.py); all six networks + `test_request_response_and_operation_contracts_match_saved_current_oas` |
| B3 `ChequeCreateRequestDto` → `ChequeCreateRequest` | required `asset`, `amount`; optional `clientChequeId`≤50, `password`≤100, `description`≤1000, `callback`, `url`, paired `targetType`/`target`≤100; all three request target types allowed | [cheque_requests.py](../src/xrocket/pay/models/cheque_requests.py); all-fields/omission/bounds/pair tests; secret password repr/dump/error/Unicode regressions; `test_request_fields_and_operation_policies_match_saved_current_oas` |
| B4 `ChequeUpdateRequestDto` → `ChequeUpdateRequest` | only optional `description`≤1000; `{}` preserves omission, `""` clears; no create fields or IDs in body | [cheque_requests.py](../src/xrocket/pay/models/cheque_requests.py); plural mutation/query-body test; `test_update_does_not_accept_create_response_or_identifier_fields` |
| B5 `AppPayoutCreateRequestDto` → `PayoutCreateRequest` | required `target`≤100, `targetType`=user_id/telegram_user_id/telegram_username, `asset`, `amount`; optional `clientPayoutId`≤50, `description` (без max), `callback` | [payout_requests.py](../src/xrocket/pay/models/payout_requests.py); exact one POST/all fields, DTO schema comparison, timeout/duplicate/manual caller lookup tests |
| B6 `MassPayoutsCreateRequestDto` → `MassPayoutCreateRequest`; `MassPayoutsPayoutRequestDto` → `MassPayoutItemRequest` | required batch `asset`, `payouts`; item required `target`≤100, `targetType`, `amount`, optional `clientPayoutId`≤50, `description`, `callback`; targetType locally only telegram_user_id (PAY-010 prose override, wider OAS enum unresolved); no inferred batch limit/splitting from invalid item maxLength500 (PAY-009) | [payout_requests.py](../src/xrocket/pay/models/payout_requests.py); empty/501 item send, reordered/duplicate results, `test_batch_fields_and_documented_policies_match_saved_current_oas` |
| B7 `WithdrawalCreateRequestDto` → `WithdrawalCreateRequest` | required `clientWithdrawalId`≤150, `network` six-code enum (required despite OAS default TON), `address`≤100, `asset`, `amount`; optional `comment`≤50, `callback`; no minLength invented. Client ID101–150 is preserved and cannot be used in GET100 lookup (PAY-016) | [withdrawal_requests.py](../src/xrocket/pay/models/withdrawal_requests.py); all networks/empty strings/lengths/exact money/ID no truncation, `test_request_fields_and_create_policy_match_saved_current_oas` |
| B8 `WithdrawalLinkRequestDto` → `WithdrawalLinkRequest` | required `network`, `address`≤100, `asset`, `amount`; optional `comment`≤50, `platform` only if supplied by xRocket; no direct withdrawal client ID/callback fields | [withdrawal_links.py](../src/xrocket/pay/models/withdrawal_links.py); every required field, all enum values, schema-allowed empties, null/extra/bypass guards; singular route/exact status tests |

Nested request schemas are distinct request classes: InvoiceCallbackRequestDto /
ChequeCallbackRequestDto / PayoutCallbackRequestDto / WithdrawalCallbackRequestDto
contain independent optional `callbackUrl`≤500 and object `payload`;
InvoiceUrlRequestDto / ChequeUrlRequestDto contain independent optional
`successUrl`/`cancelUrl`≤500. InvoiceCustomerRequestDto contains independent
optional string `id`/`email`/`telegramId`/`telegramUsername`.
No numeric local 4KB payload limit is asserted: OAS prose does not define its
encoding/byte/character metric. Empty nested objects survive serialization.

## Ответы: shapes, tolerance и evidence

| DTO group / реализация | Что проверяют synthetic fixtures/tests; практические границы |
|---|---|
| [app.py](../src/xrocket/pay/models/app.py), [currencies.py](../src/xrocket/pay/models/currencies.py), [rates.py](../src/xrocket/pay/models/rates.py) | `AppInfo` requires id/name; balances retain list and required asset/balance/available/holds; currencies are array of code/title/kind/networks with required network code; rates are array of currency/rate. `test_contracts` decodes these shapes; `test_models` checks precision/trailing zeros/future fields/networks. No success/data wrapper is invented. |
| [health.py](../src/xrocket/pay/models/health.py) | `status` required/open; component lists/name/status typed, future fields/status preserved. PAY-018 omission → None/unknown, explicit null rejected, [] distinct; tests `test_health_keeps_missing_components_unknown`, `test_health_requires_status_and_valid_provided_components`. Live omission was historical P007/P019, not a fresh run here. |
| [invoices.py](../src/xrocket/pay/models/invoices.py) | `Invoice` requires id/priceCurrency/createdAt/status/links.telegramBotLink; optional money/expiry/nested objects stay optional. Aware datetime and expiresAt datetime/null override PAY-003; future statuses/extra fields retained. `InvoicePaymentAddress` requires address/payCurrency/payNetwork/expiresAt, optional minAmount rejects explicit null. Payment-address tests distinguish exact201/required date/null/precision/unknown network. |
| [invoice_payments.py](../src/xrocket/pay/models/invoice_payments.py) | Required payment status/payAmount/payCurrency/receiveAmount/receiveCurrency/transactions; id optional PAY-007; finalizedAt datetime/null PAY-004; each internal/blockchain transaction discriminated, required id/status/createdAt, pending nullable amounts/currencies/finality PAY-005; optional tx requires all blockchain detail fields when present. Unknown transaction type is explicit raw fallback; malformed known type rejects. Tests cover both transaction kinds, unknown type/status/fields, pending/finalized, precision, aware dates and missing required fields. Finality is `finalized_at is not None`, never a guessed terminal status. |
| [cheques.py](../src/xrocket/pay/models/cheques.py) | Required chequeId/asset/links/deleted; state/targets/client ID/description/callback/url optional, nested links independently optional. OAS declares no cheque response amount: SDK does not invent it; unknown amount survives as extra. Read/write fixtures cover minimal/all nested shapes and open state/targetType. |
| [payouts.py](../src/xrocket/pay/models/payouts.py), [mass_payouts.py](../src/xrocket/pay/models/mass_payouts.py) | Required payoutId/target/targetType/asset/amount/status; callback/client ID/description optional. Mass result requires both successPayouts and errorPayouts; typed error target/targetType/amount/reason, optional client ID/description; reason requires type/title/status/detail/instance/kind. Reason status preserves finite JSON int/float. Mixed/all-success/all-error/empty/reordered/duplicate results retain server lists and IDs; has_errors/is_partial do not infer positional correlation or safe retry. |
| [withdrawals.py](../src/xrocket/pay/models/withdrawals.py), [withdrawal_links.py](../src/xrocket/pay/models/withdrawal_links.py) | Withdrawal requires withdrawalId/network/address/asset/amount; status/comment/txHash/txLink/callback optional; status remains case-sensitive/open. Quotas require withdrawMinSize/withdrawFee/withdrawFeeAsset/precision; precision finite strict int/float, separate from Money. WithdrawalLink has three independent optional string links, no at-least-one guarantee; present null rejects; no following/opening links. |
| [pagination.py](../src/xrocket/pay/models/pagination.py) | Resource list returns exactly one page; next is required nullable string; no cursor/size heuristics. Shared CursorPagination.total is optional int/None in existing SDK although OAS requires number; `test_shared_page_does_not_require_total` locks this reader tolerance. Invoice payments has a distinct next-only page, no total requirement. This tolerance is not evidence that live server omits total. |

Response models use [extra=allow](../src/xrocket/pay/models/_base.py), retain unknown
string enum values and are deliberately more tolerant than request DTOs. Existing
response `Money` accepts finite strings/integers/Decimal (float/bool reject),
where OAS wire money is string. Several optional response properties accept None
as reader tolerance, besides explicit PAY-003–005 overrides; this does not prove
upstream nullability. Health lists, address minAmount and withdrawal links have
specific present-null rejection. The matrix establishes that documented synthetic
shapes decode; it does not claim a general strict OAS conformance validator.

## Ошибки, status и shared runtime proof

All operations call the same
[transport/error pipeline](../src/xrocket/_core/transport.py), with stable
[public exceptions](../src/xrocket/_core/errors.py). Documented error statuses in
the operation table were read from each exact OAS operation. The decoder maps
401→AuthenticationError, 403→PermissionDeniedError, 404→NotFoundError,
429→RateLimitError, >=500→ServerError; remaining non-2xx→APIError. It preserves an
arbitrary JSON object as `problem`, status_code, x-request-id and retry-after;
non-object/non-JSON errors retain status with empty problem. It does not validate
every inline OAS problem subtype or expose body in ordinary exception messages.

| Scope | Evidence anchors and what they prove |
|---|---|
| Shared GET/core errors, base operation errors, invoice payments errors | [test_transport.py](../tests/test_transport.py): `test_http_error_classification_preserves_problem_and_metadata` (400/401/403/404/408/409/422/429/500/502/503), `test_html_error_keeps_http_status_without_exposing_body`, `test_invalid_success_response_is_validation_error`. These exercise app/currencies through shared transport; they are not separate endpoint-specific fixtures for every invoice-payment/base error subtype. |
| Health/read resources | `test_health_http_failure_uses_the_shared_error_pipeline`; read files above contain `test_cheque_http_errors_preserve_problem_without_retry`, `test_payout_http_errors_preserve_problem_without_retry`, `test_withdrawal_http_errors_preserve_problem_without_retry` for their methods. OAS response variants and local missing-ID guards remain distinct. |
| Every write route | Each write file above has exact status, malformed success, absent-auth and HTTP-error/no-retry tests for its operation(s). Invoice `test_invoice_write_errors_preserve_problem_metadata_and_do_not_retry`, address `test_errors_preserve_problem_metadata_without_retry`, cheque `test_mutation_errors_preserve_metadata_without_retry`, payout/withdrawal/mass `test_http_errors_preserve_problem_and_metadata_without_retry`, link `test_documented_errors_preserve_problem_metadata_without_retry`. Some suites also test an extra fallback status (e.g. mass 404, not listed by OAS). |
| Empty vs JSON response, generic success policy | [test_write_transport.py](../tests/test_write_transport.py): `test_explicit_bodyless_success_returns_none`, `test_bodyless_policy_rejects_every_nonempty_response`, `test_unexpected_2xx_is_response_validation_error`, `test_success_policy_can_explicitly_allow_multiple_statuses`; endpoint write tests verify selected exact200/exact201 policy. GET all2xx is retained D020 policy, not a write policy. |
| Request graph/bytes | [test_request_serialization.py](../tests/test_request_serialization.py) and write transport tests cover exact money/aliases/omission, nested revalidation/required fields with empty fields_set, finite JSON, response/request separation, Unicode and exact framing. DTO tests compare fields to saved OAS in invoice/address/cheque/payout/mass/withdrawal suites; link uses explicit per-field cases. |
| One attempt, auth, timeout, ownership | [test_transport.py](../tests/test_transport.py), [test_write_transport.py](../tests/test_write_transport.py), individual write files: no hidden retry/redirect, one attempt on timeout, no automatic lookup/batch splitting/link follow-up; required SDK JWT before network; injected HTTP auth/defaults untouched; SDK close blocks SDK requests and preserves caller-owned client; owned HTTP client closes. |

## Границы доказательств

В P018 отдельный ad-hoc Python pass из SDK cwd (через
`.venv/Scripts/python.exe -`, standard-library `json`/`inspect`/`ast`, без сети)
сопоставил явную карту методов с snapshot и queue: **18 paths / 25 operations,
25 unique owners, 50 sync/async methods, одинаковые signatures и literal routes**.
Проверка документа нашла все **60 distinct test-function names (63 AST locations)** и **75 relative
file links**. Это статические/интроспекционные assertions, без нового запуска
pytest внутри этого аудита; фактический offline pytest pass фиксируется отдельно
в P018 ledger/handoff. Эти числа описывают разные проверки и не складываются.

This audit found all 25 queue operations mapped to actual sync/async methods and
relevant synthetic tests; no missing route or request DTO was hidden by queue
inventory. It does **not** turn mocks into production verification. Current
snapshots can diverge from servers; PAY-001–018 unresolved details retain their
status in [pay-api.md](pay-api.md). Historical public testnet rates/currencies
passes, health deviation and P019 correction, private skips/fixtures absent,
and no live mutations/webhooks are recorded in
[live-verification.md](live-verification.md) and historical
[verification.md](verification.md). No new live calls, JWT lookup or user payload
inspection were used for this matrix.

Webhooks are outside the 25 REST inventory; their separate proof is
[test_webhook_signatures.py](../tests/test_webhook_signatures.py) and
[test_webhook_events.py](../tests/test_webhook_events.py), Current OAS
`info.description`/webhook schemas and PAY overrides. Synthetic signatures do
not prove real delivery, retries/order, replay storage, deduplication, settlement
or upstream idempotency. Platform/Python-version coverage belongs to the dated
readiness ledger and must not be inferred from this source audit.
