"""Exercise the real live harness offline, including its gates and safe failures."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "p007-synthetic-token"
PRIVATE_RECORD = "p007-synthetic-private-record"
IDS = {
    f"XROCKET_PAY_TESTNET_{prefix}{resource}_ID": f"p007-synthetic-{prefix}{resource}"
    for resource in ("INVOICE", "CHEQUE", "PAYOUT", "WITHDRAWAL")
    for prefix in ("", "CLIENT_")
}

# A child process imports and runs the integration tests with HTTPX send patched.
# No production test fixture, token, or response is read or persisted.
RUNNER = r"""
import json
import os
import httpx
import pytest

calls = []
reports = []
deselected = 0
mode = os.environ["P007_MOCK_MODE"]
private_record = "p007-synthetic-private-record"
invoice = {
    "id": "synthetic-invoice", "priceCurrency": "USDT", "createdAt": "2026-10-17T00:00:00Z",
    "status": "active", "links": {"telegramBotLink": "https://example.invalid"},
}
cheque = {"chequeId": "synthetic-cheque", "asset": "USDT", "links": {}, "deleted": False}
payout = {
    "payoutId": "synthetic-payout", "target": private_record, "targetType": "user_id",
    "asset": "USDT", "amount": "0.00100", "status": "pending",
}
withdrawal = {
    "withdrawalId": "synthetic-withdrawal", "network": "TON", "address": private_record,
    "asset": "USDT", "amount": "0.00100",
}
def page(item):
    return {"items": [item], "pagination": {"total": 1, "next": None}}
payloads = {
    "/health": {"status": "ok"},
    "/api/v1/currencies": [{
        "code": "USDT", "title": "Tether", "kind": "crypto", "networks": [{"code": "TON"}],
    }],
    "/api/v1/rates": [{"currency": "BTC", "rate": "1.1"}, {"currency": "ETH", "rate": "2.2"}],
    "/api/v1/app-info": {"id": "synthetic-app", "name": private_record},
    "/api/v1/balances": {"balances": []},
    "/api/v1/invoices": page(invoice),
    "/api/v1/invoice": invoice,
    "/api/v1/invoice/payments": {"items": [], "pagination": {"next": None}},
    "/api/v1/cheques": page(cheque),
    "/api/v1/cheque": cheque,
    "/api/v1/payouts": page(payout),
    "/api/v1/payout": payout,
    "/api/v1/withdrawals": page(withdrawal),
    "/api/v1/withdrawal": withdrawal,
    "/api/v1/withdrawal-quotas": {
        "withdrawMinSize": "0.00100", "withdrawFee": "0.00010",
        "withdrawFeeAsset": "TON", "precision": 6,
    },
}
public = {"/health", "/api/v1/currencies", "/api/v1/rates"}
def respond(request):
    calls.append(request.url.path)
    if request.method != "GET" or request.url.host != "pay.api.testnet.xrocket.exchange":
        raise RuntimeError("Harness must use testnet GET only")
    if request.url.path in public:
        if "authorization" in request.headers:
            raise RuntimeError("Public smoke inherited a private token")
        if mode == "public_failure":
            raise httpx.ConnectError("Synthetic unavailable testnet", request=request)
    else:
        if request.headers.get("authorization") != "Bearer p007-synthetic-token":
            raise RuntimeError("Private smoke did not use the explicit testnet token")
        for name, value in request.url.params.multi_items():
            if name.endswith("Id") and value not in os.environ.values():
                raise RuntimeError("Identifier did not come from an explicit fixture")
        if mode == "private_failure":
            return httpx.Response(500, json={"detail": private_record}, request=request)
    return httpx.Response(200, json=payloads[request.url.path], request=request)
def sync_send(self, request, **kwargs):
    return respond(request)
async def async_send(self, request, **kwargs):
    return respond(request)
httpx.Client.send = sync_send
httpx.AsyncClient.send = async_send
class Reports:
    def pytest_runtest_logreport(self, report):
        if report.when == "call" or report.failed or report.skipped:
            reports.append(report.outcome)
    def pytest_deselected(self, items):
        global deselected
        deselected += len(items)
args = [
    "tests/integration", "-q", "--tb=short", "--show-capture=no", "-p", "no:cacheprovider",
    "-o", "asyncio_default_test_loop_scope=session",
]
if mode != "default_selection":
    args += ["-m", "live"]
code = pytest.main(args, plugins=[Reports()])
print("P007_SUMMARY:" + json.dumps({
    "exit_code": int(code), "passed": reports.count("passed"), "failed": reports.count("failed"),
    "skipped": reports.count("skipped"), "deselected": deselected, "calls": calls,
}))
"""


def _run(mode: str, env_values: dict[str, str]) -> dict[str, Any]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("XROCKET_", "PYTEST_"))
    }
    env.update(env_values)
    env["P007_MOCK_MODE"] = mode
    completed = subprocess.run(
        [sys.executable, "-c", RUNNER],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert TOKEN not in output
    assert PRIVATE_RECORD not in output
    assert all(value not in output for value in IDS.values())
    assert "P007_SUMMARY:" in completed.stdout
    result: dict[str, Any] = json.loads(completed.stdout.rsplit("P007_SUMMARY:", 1)[1])
    return result


ALL_FIXTURES = {
    "XROCKET_RUN_LIVE": "1",
    "XROCKET_PAY_TESTNET_TOKEN": TOKEN,
    "XROCKET_PAY_TESTNET_QUOTAS_NETWORK": "TON",
    "XROCKET_PAY_TESTNET_QUOTAS_ASSET": "USDT",
    **IDS,
}


@pytest.mark.parametrize(
    ("mode", "env_values", "passed", "failed", "skipped", "deselected", "requests"),
    [
        ("default_selection", ALL_FIXTURES, 0, 0, 0, 40, 0),
        ("success", {**ALL_FIXTURES, "XROCKET_RUN_LIVE": "0"}, 0, 0, 40, 0, 0),
        ("success", {"XROCKET_RUN_LIVE": "1"}, 6, 0, 34, 0, 6),
        (
            "success",
            {"XROCKET_RUN_LIVE": "1", "XROCKET_PAY_TESTNET_TOKEN": TOKEN},
            18,
            0,
            22,
            0,
            18,
        ),
        ("success", ALL_FIXTURES, 40, 0, 0, 0, 40),
        (
            "success",
            {
                key: value
                for key, value in ALL_FIXTURES.items()
                if key
                not in {
                    "XROCKET_PAY_TESTNET_INVOICE_ID",
                    "XROCKET_PAY_TESTNET_CLIENT_INVOICE_ID",
                    "XROCKET_PAY_TESTNET_QUOTAS_ASSET",
                }
            },
            30,
            0,
            10,
            0,
            30,
        ),
        ("private_failure", ALL_FIXTURES, 6, 34, 0, 0, 40),
        ("public_failure", {"XROCKET_RUN_LIVE": "1"}, 0, 6, 34, 0, 6),
    ],
    ids=[
        "offline-default",
        "explicit-opt-out",
        "no-jwt",
        "no-ids",
        "all-fixtures",
        "partial-fixtures",
        "private-failure-is-not-skip",
        "unavailable-testnet-is-not-skip",
    ],
)
def test_live_harness_gates_and_requests_without_network(
    mode: str,
    env_values: dict[str, str],
    passed: int,
    failed: int,
    skipped: int,
    deselected: int,
    requests: int,
) -> None:
    result = _run(mode, env_values)
    assert {key: result[key] for key in ("passed", "failed", "skipped", "deselected")} == {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "deselected": deselected,
    }
    assert len(result["calls"]) == requests
    assert result["exit_code"] == (5 if deselected else 1 if failed else 0)
    if passed == 40:
        assert len(set(result["calls"])) == 15
