# Exchange REST inventory: 2026-10-18

Источник — неизменённый [Exchange OAS](openapi/exchange-current.json),
[provenance](openapi/manifest.json); discovery, interpretations и open issues —
в [Exchange spec](exchange-api.md). 23 paths, 26 операций: 21 GET / 4 POST / 1 DELETE;
10 public по OAS / 16 bearer. WebSocket inventory и lifecycle — [отдельно](exchange-websocket.md).

Каждая строка буквально соответствует `paths[path][method]`; operationId помогает
проверить точный pointer. Success DTO — schema соответствующего response status,
error column — только перечисленные OAS response statuses, не исчерпывающая
гарантия поведения сервера. Public означает отсутствие operation/root security.
Fees/quotas имеют bearer вопреки неполной auth маркировке reference (EX-001).

Queue owner — **planned coverage**, не implemented SDK method. X010–X013 владеют
исследованием private contracts; будущие implementation cards получат ownership
явной передачей без дубликатов. X014 — WS gate, без REST operations. Все новые
карточки вне сохранённого autopilot scope; единственный первый public результат — X002.

| HTTP method/path | operationId | Auth | Success/schema | OAS errors | Owner |
|---|---|---|---|---|---|
| `GET /api/v1/accounts/trading/balances` | `ExchangeAccountController_getAccountBalances` | bearer | 200 `TradingBalancesResponse` | 403, 500 | [X010](../workflow/tasks/X010.md) |
| `GET /api/v1/trade-fees` | `ExchangeAccountController_getTradeFees` | bearer | 200 `TradeFeesResponse` | 400, 403, 404, 500 | [X010](../workflow/tasks/X010.md) |
| `GET /api/v1/assets` | `ExchangeMarketDataAssetController_getAssets` | public (OAS) | 200 `AssetsResponse` | 500 | [X003](../workflow/tasks/X003.md) |
| `GET /api/v1/assets/{asset}` | `ExchangeMarketDataAssetController_getAsset` | public (OAS) | 200 `AssetResponse` | 404, 500 | [X003](../workflow/tasks/X003.md) |
| `GET /api/v1/symbols` | `ExchangeMarketDataController_getSymbols` | public (OAS) | 200 `SymbolsResponse` | 500 | [X002](../workflow/tasks/X002.md) |
| `GET /api/v1/symbols/{symbol}` | `ExchangeMarketDataController_getSymbol` | public (OAS) | 200 `SymbolResponse` | 400, 404, 500 | [X002](../workflow/tasks/X002.md) |
| `GET /api/v1/ticker/{tickerType}` | `ExchangeMarketDataController_getTicker` | public (OAS) | 200 `TickersResponse` | 400, 404, 500 | [X004](../workflow/tasks/X004.md) |
| `GET /api/v1/candles` | `ExchangeMarketDataController_getCandles` | public (OAS) | 200 `CandlesResponse` | 400, 403, 404, 500 | [X005](../workflow/tasks/X005.md) |
| `GET /api/v1/orderbook` | `ExchangeMarketDataController_getOrderbook` | public (OAS) | 200 `OrderbookResponse` | 400, 404, 500 | [X006](../workflow/tasks/X006.md) |
| `GET /api/v1/trades` | `ExchangeMarketDataController_getTrades` | public (OAS) | 200 `TradesResponse` | 400, 403, 404, 500 | [X007](../workflow/tasks/X007.md) |
| `GET /api/v1/rates` | `ExchangeRatesController_getRates` | public (OAS) | 200 `asset-keyed map → AssetRateResponse` | 400, 403, 404, 500 | [X008](../workflow/tasks/X008.md) |
| `GET /api/v1/orders/active` | `ExchangeOrderController_getActiveOrders` | bearer | 200 `ActiveOrdersResponse` | 403, 500 | [X011](../workflow/tasks/X011.md) |
| `GET /api/v1/order` | `ExchangeOrderController_getOrder` | bearer | 200 `oneOf(LimitOrderResponse, MarketOrderResponse, StopLimitOrderResponse, StopMarketOrderResponse)` | 400, 403, 404, 500 | [X011](../workflow/tasks/X011.md) |
| `DELETE /api/v1/order` | `ExchangeOrderController_cancelOrder` | bearer | 200 `CancelOrderResponse` | 400, 403, 404, 500 | [X011](../workflow/tasks/X011.md) |
| `POST /api/v1/orders` | `ExchangeOrderController_placeOrder` | bearer | 201 `oneOf(LimitOrderResponse, MarketOrderResponse, StopLimitOrderResponse, StopMarketOrderResponse)` | 400, 403, 404, 500 | [X011](../workflow/tasks/X011.md) |
| `GET /api/v1/orders/history` | `ExchangeOrderController_getOrdersHistory` | bearer | 200 `OrderHistoryResponse` | 400, 403, 404, 500 | [X011](../workflow/tasks/X011.md) |
| `POST /api/v1/accounts/transfers` | `ExchangeTransferController_transfer` | bearer | 201 `CreateTransferResponse` | 400, 403, 404, 500 | [X013](../workflow/tasks/X013.md) |
| `GET /api/v1/accounts/transfers` | `ExchangeTransferController_getTransfers` | bearer | 200 `TransfersResponse` | 400, 404, 500 | [X013](../workflow/tasks/X013.md) |
| `GET /api/v1/accounts/transfer` | `ExchangeTransferController_getTransferByTransferId` | bearer | 200 `TransferResponse` | 400, 404, 500 | [X013](../workflow/tasks/X013.md) |
| `POST /api/v1/orders/estimate` | `ExchangeOrderEstimateController_estimateOrder` | bearer | 201 `oneOf(EstimateLimitOrderResponse, EstimateMarketOrderResponse, EstimateStopLimitOrderResponse, EstimateStopMarketOrderResponse)` | 400, 403, 404, 500 | [X011](../workflow/tasks/X011.md) |
| `GET /health` | `HealthController_health` | public (OAS) | 200 `inline health object` | — | [X009](../workflow/tasks/X009.md) |
| `GET /api/v1/accounts/funding/balances` | `WalletFundingController_getAccountBalances` | bearer | 200 `FundingBalancesResponse` | 403, 500 | [X012](../workflow/tasks/X012.md) |
| `GET /api/v1/accounts/funding/withdrawal-quotas` | `WalletFundingController_getWithdrawalQuotas` | bearer | 200 `WithdrawalQuotasResponse` | 400, 403, 404, 500 | [X012](../workflow/tasks/X012.md) |
| `POST /api/v1/accounts/funding/withdrawals` | `WalletFundingController_createWithdrawal` | bearer | 201 `WithdrawalDetailsResponse` | 400, 403, 404, 500 | [X012](../workflow/tasks/X012.md) |
| `GET /api/v1/accounts/funding/withdrawals` | `WalletFundingController_getWithdrawals` | bearer | 200 `WithdrawalsResponse` | 400, 403, 404, 500 | [X012](../workflow/tasks/X012.md) |
| `GET /api/v1/accounts/funding/withdrawal` | `WalletFundingController_getWithdrawal` | bearer | 200 `WithdrawalDetailsResponse` | 400, 403, 404, 500 | [X012](../workflow/tasks/X012.md) |
