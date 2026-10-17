"""Synthetic Current Pay withdrawal reads, shared by sync and async clients."""

import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from xrocket import (
    APIError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ResponseValidationError,
    ServerError,
    pay,
)
from xrocket.pay import (
    AsyncPayClient,
    CursorPage,
    PayClient,
    Withdrawal,
    WithdrawalCallback,
    WithdrawalQuotas,
    models,
)

Client = PayClient | AsyncPayClient
Handler = Callable[[httpx.Request], httpx.Response]
FROM_DATE = datetime.fromisoformat("2026-10-16T21:02:03.123456-07:00")
TO_DATE = datetime.fromisoformat("2026-10-17T09:10:11+05:00")
EXACT_AMOUNT = "12345678901234567890.1234567890123456789000"
EXACT_FEE = "0.000000000000000000123456789000"


def _withdrawal(**overrides: Any) -> dict[str, Any]:
    return {
        "withdrawalId": "000-withdrawal",
        "network": "TON",
        "address": "synthetic-address",
        "asset": "USDT",
        "amount": EXACT_AMOUNT,
        **overrides,
    }


def _quotas(**overrides: Any) -> dict[str, Any]:
    return {
        "withdrawMinSize": EXACT_AMOUNT,
        "withdrawFee": EXACT_FEE,
        "withdrawFeeAsset": "TON",
        "precision": 6,
        **overrides,
    }


def _page(items: list[dict[str, Any]], next_cursor: str | None = None) -> dict[str, Any]:
    return {"items": items, "pagination": {"total": len(items), "next": next_cursor}}


def _kwargs(method: str) -> dict[str, Any]:
    if method == "retrieve":
        return {"withdrawal_id": "withdrawal"}
    if method == "quotas":
        return {"network": "TON", "asset": "USDT"}
    return {}


@pytest.fixture(params=("sync", "async"))
def backend(request: pytest.FixtureRequest) -> str:
    return str(request.param)


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


@asynccontextmanager
async def _sdk(
    backend: str, handler: Handler, *, api_token: str | None = "synthetic-test-token"
) -> AsyncIterator[Client]:
    transport = httpx.MockTransport(handler)
    if backend == "async":
        http: httpx.Client | httpx.AsyncClient = httpx.AsyncClient(transport=transport)
        client: Client = AsyncPayClient(
            api_token=api_token, http_client=http, environment="testnet"
        )
    else:
        http = httpx.Client(transport=transport)
        client = PayClient(api_token=api_token, http_client=http, environment="testnet")
    try:
        yield client
    finally:
        if isinstance(client, AsyncPayClient):
            await client.aclose()
        else:
            client.close()
        if isinstance(http, httpx.AsyncClient):
            await http.aclose()
        else:
            http.close()


@pytest.mark.parametrize("name", ["Withdrawal", "WithdrawalCallback", "WithdrawalQuotas"])
def test_withdrawal_models_share_public_exports(name: str) -> None:
    assert name in pay.__all__
    assert name in models.__all__
    assert getattr(pay, name) is getattr(models, name)


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("list", ["from_date", "to_date", "status", "cursor", "limit"]),
        ("retrieve", ["withdrawal_id", "client_withdrawal_id"]),
        ("quotas", ["network", "asset"]),
    ],
)
async def test_withdrawal_sync_async_signatures_match(method: str, expected: list[str]) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("Inspecting resource signatures reached the network")

    async with (
        _sdk("sync", unexpected_request) as sync,
        _sdk("async", unexpected_request) as asynchronous,
    ):
        sync_method = getattr(sync.withdrawals, method)
        async_method = getattr(asynchronous.withdrawals, method)
        assert inspect.signature(sync_method) == inspect.signature(async_method)
        parameters = inspect.signature(sync_method).parameters
        assert list(parameters) == expected
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
        expected_default = inspect.Parameter.empty if method == "quotas" else None
        assert all(p.default is expected_default for p in parameters.values())
        assert not inspect.iscoroutinefunction(sync_method)
        assert inspect.iscoroutinefunction(async_method)


@pytest.mark.parametrize(
    ("method", "kwargs", "path", "wire"),
    [
        ("list", {}, "/api/v1/withdrawals", {}),
        (
            "list",
            {"from_date": None, "to_date": None, "status": None, "cursor": None, "limit": None},
            "/api/v1/withdrawals",
            {},
        ),
        (
            "list",
            {
                "from_date": FROM_DATE,
                "to_date": TO_DATE,
                "status": "COMPLETED",
                "cursor": "opaque+/= cursor?&\u2603",
                "limit": 1,
            },
            "/api/v1/withdrawals",
            {
                "fromDate": FROM_DATE.isoformat(),
                "toDate": TO_DATE.isoformat(),
                "status": "COMPLETED",
                "cursor": "opaque+/= cursor?&\u2603",
                "limit": "1",
            },
        ),
        (
            "list",
            {"from_date": FROM_DATE, "status": "CREATED"},
            "/api/v1/withdrawals",
            {"fromDate": FROM_DATE.isoformat(), "status": "CREATED"},
        ),
        (
            "list",
            {"to_date": TO_DATE, "status": "FAIL", "cursor": ""},
            "/api/v1/withdrawals",
            {"toDate": TO_DATE.isoformat(), "status": "FAIL", "cursor": ""},
        ),
        (
            "list",
            {"from_date": TO_DATE, "to_date": FROM_DATE},
            "/api/v1/withdrawals",
            {"fromDate": TO_DATE.isoformat(), "toDate": FROM_DATE.isoformat()},
        ),
        *(
            ("list", {"limit": limit}, "/api/v1/withdrawals", {"limit": str(limit)})
            for limit in (0, -1, 1001)
        ),
        (
            "retrieve",
            {"withdrawal_id": "w"},
            "/api/v1/withdrawal",
            {"withdrawalId": "w"},
        ),
        (
            "retrieve",
            {"withdrawal_id": "000-withdrawal", "client_withdrawal_id": None},
            "/api/v1/withdrawal",
            {"withdrawalId": "000-withdrawal"},
        ),
        (
            "retrieve",
            {"withdrawal_id": None, "client_withdrawal_id": "order /+?"},
            "/api/v1/withdrawal",
            {"clientWithdrawalId": "order /+?"},
        ),
        (
            "retrieve",
            {"withdrawal_id": "withdrawal", "client_withdrawal_id": "client-withdrawal"},
            "/api/v1/withdrawal",
            {"withdrawalId": "withdrawal", "clientWithdrawalId": "client-withdrawal"},
        ),
        (
            "retrieve",
            {"withdrawal_id": "w" * 100, "client_withdrawal_id": "o" * 100},
            "/api/v1/withdrawal",
            {"withdrawalId": "w" * 100, "clientWithdrawalId": "o" * 100},
        ),
        *(
            (
                "quotas",
                {"network": network, "asset": "USDT"},
                "/api/v1/withdrawal-quotas",
                {"network": network, "asset": "USDT"},
            )
            for network in ("TON", "BSC", "ETH", "BTC", "TRX", "SOL")
        ),
        (
            "quotas",
            {"network": "TON", "asset": ""},
            "/api/v1/withdrawal-quotas",
            {"network": "TON", "asset": ""},
        ),
        (
            "quotas",
            {"network": "ETH", "asset": "synthetic /+?"},
            "/api/v1/withdrawal-quotas",
            {"network": "ETH", "asset": "synthetic /+?"},
        ),
    ],
)
async def test_withdrawal_routes_queries_and_minimal_response(
    backend: str, method: str, kwargs: dict[str, Any], path: str, wire: dict[str, str]
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        payload = _page([_withdrawal()]) if method == "list" else _withdrawal()
        return httpx.Response(200, json=_quotas() if method == "quotas" else payload)

    async with _sdk(backend, respond) as client:
        result = await _resolve(getattr(client.withdrawals, method)(**kwargs))

    assert len(calls) == 1
    request = calls[0]
    assert request.method == "GET"
    assert request.url.host == "pay.api.testnet.xrocket.exchange"
    assert request.url.path == path
    assert dict(request.url.params) == wire
    assert request.headers["Authorization"] == "Bearer synthetic-test-token"
    assert request.headers["Accept"] == "application/json"
    assert "Rocket-Pay-Key" not in request.headers
    if method == "quotas":
        assert isinstance(result, WithdrawalQuotas)
        assert isinstance(result.withdraw_min_size, Decimal)
        assert isinstance(result.withdraw_fee, Decimal)
        assert str(result.withdraw_min_size) == EXACT_AMOUNT
        assert str(result.withdraw_fee) == str(Decimal(EXACT_FEE))
        assert result.withdraw_fee_asset == "TON"
        assert type(result.precision) is int
        assert result.precision == 6
        return
    if method == "list":
        assert isinstance(result, CursorPage)
        result = result.items[0]
    assert isinstance(result, Withdrawal)
    assert result.withdrawal_id == "000-withdrawal"
    assert result.network == "TON"
    assert result.address == "synthetic-address"
    assert result.asset == "USDT"
    assert isinstance(result.amount, Decimal)
    assert str(result.amount) == EXACT_AMOUNT
    assert result.status is result.comment is result.tx_hash is result.tx_link is None
    assert result.callback is None


@pytest.mark.parametrize("next_cursor", [None, "next+/= cursor"])
@pytest.mark.parametrize("item_count", [0, 1])
async def test_withdrawal_pagination_returns_one_page_without_following_next(
    backend: str, next_cursor: str | None, item_count: int
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_page([_withdrawal()] * item_count, next_cursor))

    async with _sdk(backend, respond) as client:
        page = await _resolve(client.withdrawals.list(limit=1))

    assert len(calls) == 1
    assert len(page.items) == item_count
    assert page.pagination.total == item_count
    assert page.pagination.next == next_cursor


@pytest.mark.parametrize("method", ["list", "retrieve"])
async def test_withdrawal_nested_response_preserves_unknown_network_status_and_fields(
    backend: str, method: str
) -> None:
    payload = _withdrawal(
        network="FUTURE_NETWORK",
        status="FUTURE_STATUS",
        comment="Synthetic fixture",
        txHash="synthetic-hash",
        txLink="https://example.invalid/transaction",
        callback={
            "callbackUrl": "https://example.invalid/callback",
            "payload": {"order": "synthetic", "nested": {"items": [1, True, None]}},
            "callbackExtra": True,
        },
        futureField={"version": 2},
    )
    response = _page([payload]) if method == "list" else payload
    if method == "list":
        response["pageExtra"] = True
        response["pagination"]["cursorVersion"] = 2
    async with _sdk(backend, lambda _: httpx.Response(200, json=response)) as client:
        result = await _resolve(getattr(client.withdrawals, method)(**_kwargs(method)))
    if method == "list":
        assert result.model_extra == {"pageExtra": True}
        assert result.pagination.model_extra == {"cursorVersion": 2}
        result = result.items[0]

    assert isinstance(result, Withdrawal)
    assert result.network == "FUTURE_NETWORK"
    assert result.status == "FUTURE_STATUS"
    assert result.comment == "Synthetic fixture"
    assert result.tx_hash == "synthetic-hash"
    assert result.tx_link == "https://example.invalid/transaction"
    assert result.model_extra == {"futureField": {"version": 2}}
    assert isinstance(result.callback, WithdrawalCallback)
    assert result.callback.callback_url == "https://example.invalid/callback"
    assert result.callback.payload == payload["callback"]["payload"]
    assert result.callback.model_extra == {"callbackExtra": True}
    dumped = result.model_dump(mode="json", by_alias=True)
    assert dumped["withdrawalId"] == "000-withdrawal"
    assert dumped["txHash"] == "synthetic-hash"
    assert dumped["txLink"] == "https://example.invalid/transaction"
    assert dumped["amount"] == EXACT_AMOUNT
    assert dumped["callback"]["callbackUrl"] == "https://example.invalid/callback"


@pytest.mark.parametrize("status", ["CREATED", "COMPLETED", "FAIL"])
def test_withdrawal_known_uppercase_response_statuses_remain_literal(status: str) -> None:
    assert Withdrawal.model_validate(_withdrawal(status=status)).status == status


@pytest.mark.parametrize(
    "callback", [{}, {"callbackUrl": "https://example.invalid/callback"}, {"payload": {}}]
)
def test_withdrawal_callback_fields_are_independently_optional(callback: dict[str, Any]) -> None:
    withdrawal = Withdrawal.model_validate(_withdrawal(callback=callback))
    assert isinstance(withdrawal.callback, WithdrawalCallback)
    assert withdrawal.callback.callback_url == callback.get("callbackUrl")
    assert withdrawal.callback.payload == callback.get("payload")


@pytest.mark.parametrize("field", ["withdrawalId", "network", "address", "asset", "amount"])
def test_withdrawal_requires_documented_required_fields(field: str) -> None:
    payload = _withdrawal()
    del payload[field]
    with pytest.raises(ValidationError):
        Withdrawal.model_validate(payload)


@pytest.mark.parametrize(
    "field", ["withdrawMinSize", "withdrawFee", "withdrawFeeAsset", "precision"]
)
def test_withdrawal_quotas_requires_all_documented_fields(field: str) -> None:
    payload = _quotas()
    del payload[field]
    with pytest.raises(ValidationError):
        WithdrawalQuotas.model_validate(payload)


@pytest.mark.parametrize("precision", [6, 6.0, 6.5, 0, -1])
async def test_quotas_precision_preserves_json_number_type_and_extra_fields(
    backend: str, precision: int | float
) -> None:
    payload = _quotas(precision=precision, futureField={"version": 2})
    async with _sdk(backend, lambda _: httpx.Response(200, json=payload)) as client:
        result = await _resolve(client.withdrawals.quotas(network="TON", asset="USDT"))

    assert isinstance(result, WithdrawalQuotas)
    assert type(result.precision) is type(precision)
    assert result.precision == precision
    assert result.model_extra == {"futureField": {"version": 2}}
    dumped = result.model_dump(mode="json", by_alias=True)
    assert dumped["withdrawMinSize"] == EXACT_AMOUNT
    assert dumped["withdrawFee"] == str(Decimal(EXACT_FEE))
    assert dumped["withdrawFeeAsset"] == "TON"
    assert type(dumped["precision"]) is type(precision)


@pytest.mark.parametrize(
    "precision", [True, False, "6", "6.5", None, float("nan"), float("inf"), float("-inf")]
)
def test_quotas_precision_rejects_non_numeric_or_non_finite_values(precision: Any) -> None:
    with pytest.raises(ValidationError):
        WithdrawalQuotas.model_validate(_quotas(precision=precision))


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        # Missing identifiers are rejected by SDK policy, not a claimed upstream 400 contract.
        ("retrieve", {}),
        ("retrieve", {"withdrawal_id": None, "client_withdrawal_id": None}),
        *(
            ("retrieve", {field: value})
            for field in ("withdrawal_id", "client_withdrawal_id")
            for value in ("", "x" * 101, 123, True)
        ),
        # Create's 150-character allowance must not widen the GET limit of 100.
        ("retrieve", {"client_withdrawal_id": "x" * 150}),
        ("retrieve", {"withdrawal_id": "valid", "client_withdrawal_id": ""}),
        ("retrieve", {"withdrawal_id": "", "client_withdrawal_id": "valid"}),
        *(("list", {"limit": value}) for value in (True, False, 1.5, "1")),
        *(("list", {"status": value}) for value in ("created", "completed", "fail", "FUTURE", 1)),
        *(
            ("list", {field: value})
            for field in ("from_date", "to_date")
            for value in (datetime(2026, 10, 17), date(2026, 10, 17), "2026-10-17T09:00:00Z")
        ),
        *(
            ("quotas", {"network": value, "asset": "USDT"})
            for value in (None, "ton", "FUTURE", "", 1, True)
        ),
        *(("quotas", {"network": "TON", "asset": value}) for value in (None, 1, True)),
    ],
)
async def test_invalid_withdrawal_arguments_fail_before_network(
    backend: str, method: str, kwargs: dict[str, Any]
) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid withdrawal arguments reached the network")

    async with _sdk(backend, unexpected_request) as client:
        with pytest.raises(ValueError):
            await _resolve(getattr(client.withdrawals, method)(**kwargs))


@pytest.mark.parametrize("kwargs", [{}, {"network": "TON"}, {"asset": "USDT"}])
async def test_quotas_query_arguments_are_required(backend: str, kwargs: dict[str, Any]) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("Quotas without required arguments reached the network")

    async with _sdk(backend, unexpected_request) as client:
        with pytest.raises(TypeError):
            await _resolve(client.withdrawals.quotas(**kwargs))


@pytest.mark.parametrize("method", ["list", "retrieve", "quotas"])
async def test_withdrawal_reads_require_sdk_auth_before_network(backend: str, method: str) -> None:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("An unauthenticated withdrawal request reached the network")

    async with _sdk(backend, unexpected_request, api_token=None) as client:
        with pytest.raises(AuthenticationError):
            await _resolve(getattr(client.withdrawals, method)(**_kwargs(method)))


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("retrieve", {}),
        ("retrieve", _withdrawal(amount=0.1)),
        ("retrieve", _withdrawal(amount=True)),
        ("retrieve", _withdrawal(amount="NaN")),
        ("retrieve", _withdrawal(callback={"payload": ["not-an-object"]})),
        ("list", {"items": [_withdrawal()], "pagination": {}}),
        ("list", {"items": [_withdrawal()], "pagination": {"total": 1}}),
        ("list", _page([{}])),
        ("list", _page([_withdrawal(amount=0.1)])),
        ("list", {"pagination": {"total": 0, "next": None}}),
        ("quotas", {}),
        ("quotas", _quotas(withdrawMinSize=0.1)),
        ("quotas", _quotas(withdrawFee=0.1)),
        ("quotas", _quotas(withdrawMinSize=True)),
        ("quotas", _quotas(withdrawFee="Infinity")),
        ("quotas", _quotas(precision=True)),
        ("quotas", _quotas(precision="6")),
    ],
)
async def test_malformed_withdrawal_responses_use_shared_validation_error(
    backend: str, method: str, payload: dict[str, Any]
) -> None:
    async with _sdk(backend, lambda _: httpx.Response(200, json=payload)) as client:
        with pytest.raises(ResponseValidationError):
            await _resolve(getattr(client.withdrawals, method)(**_kwargs(method)))


@pytest.mark.parametrize(
    ("method", "status", "error_type"),
    [
        ("list", 401, AuthenticationError),
        ("retrieve", 401, AuthenticationError),
        ("quotas", 401, AuthenticationError),
        ("retrieve", 404, NotFoundError),
        ("list", 429, RateLimitError),
        ("retrieve", 429, RateLimitError),
        ("quotas", 429, RateLimitError),
        ("list", 500, ServerError),
        ("retrieve", 500, ServerError),
        ("quotas", 500, ServerError),
    ],
)
async def test_withdrawal_http_errors_preserve_problem_without_retry(
    backend: str, method: str, status: int, error_type: type[APIError]
) -> None:
    calls: list[httpx.Request] = []
    problem = {"status": status, "kind": "synthetic", "detail": "Synthetic failure"}

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=problem, headers={"x-request-id": "withdrawal-request"})

    async with _sdk(backend, respond) as client:
        with pytest.raises(error_type) as caught:
            await _resolve(getattr(client.withdrawals, method)(**_kwargs(method)))

    assert type(caught.value) is error_type
    assert caught.value.status_code == status
    assert caught.value.problem == problem
    assert caught.value.request_id == "withdrawal-request"
    assert len(calls) == 1
