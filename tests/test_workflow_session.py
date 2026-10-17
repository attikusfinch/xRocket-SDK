"""Validate product ownership and session safeguards with isolated workflow files."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "session.py"
MODULE_SPEC = importlib.util.spec_from_file_location("workflow_session", SCRIPT)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
session = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(session)


def _write_queue(document: dict[str, Any]) -> None:
    (session.WORKFLOW / "tasks.json").write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def queue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(session, "ROOT", tmp_path)
    monkeypatch.setattr(session, "WORKFLOW", tmp_path / "workflow")
    for folder in ("workflow/tasks", "workflow/handoffs", "spec/openapi"):
        (tmp_path / folder).mkdir(parents=True)
    pay_paths = ["/health", *(f"/pay/{index}" for index in range(24))]
    for product, paths in (("pay", pay_paths), ("exchange", ["/health", "/markets"])):
        snapshot = {
            "openapi": "3.0.0",
            "paths": {
                path: {
                    "get": {"responses": {"200": {"description": "Synthetic response"}}},
                    "parameters": [],
                    "summary": "Path metadata is not a REST operation",
                }
                for path in paths
            },
        }
        (tmp_path / "spec/openapi" / f"{product}-current.json").write_text(
            json.dumps(snapshot), encoding="utf-8"
        )
    tasks = [
        {
            "id": "PAY",
            "title": "Synthetic Pay baseline",
            "status": "done",
            "depends_on": [],
            "card": "tasks/PAY.md",
            "handoff": "handoffs/PAY-01.md",
            "operations": [{"product": "pay", "method": "GET", "path": path} for path in pay_paths],
        },
        {
            "id": "XPUBLIC",
            "title": "Synthetic public Exchange slice",
            "status": "todo",
            "depends_on": ["PAY"],
            "card": "tasks/XPUBLIC.md",
            "handoff": None,
            "operations": [{"product": "exchange", "method": "GET", "path": "/health"}],
        },
        {
            "id": "XLATER",
            "title": "Synthetic later Exchange slice",
            "status": "todo",
            "depends_on": ["XPUBLIC"],
            "card": "tasks/XLATER.md",
            "handoff": None,
            "operations": [{"product": "exchange", "method": "GET", "path": "/markets"}],
        },
    ]
    for task in tasks:
        (session.WORKFLOW / task["card"]).write_text(task["title"], encoding="utf-8")
    (session.WORKFLOW / "handoffs/PAY-01.md").write_text("Synthetic handoff", encoding="utf-8")
    document = {"version": 2, "tasks": tasks}
    _write_queue(document)
    return document


def test_independent_products_allow_same_method_path(queue: dict[str, Any]) -> None:
    tasks = session.load_tasks()
    assert tasks == queue["tasks"]
    assert [task["id"] for task in session.available(tasks)] == ["XPUBLIC"]


def test_check_reports_each_product_and_stays_read_only(
    queue: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    before = {path: path.read_bytes() for path in session.ROOT.rglob("*") if path.is_file()}
    monkeypatch.setattr("sys.argv", ["session.py", "check"])
    assert session.main() == 0
    output = capsys.readouterr().out
    assert "Pay snapshot operations: 25, all covered exactly once" in output
    assert "Exchange snapshot operations: 2, all covered exactly once" in output
    assert output.count("planned coverage, not runtime support") == 2
    assert "Ready: XPUBLIC" in output
    assert before == {path: path.read_bytes() for path in session.ROOT.rglob("*") if path.is_file()}


@pytest.mark.parametrize("product", [None, "", "Pay", "other", 1, [], {}])
def test_operation_requires_known_explicit_product(
    queue: dict[str, Any], product: Any
) -> None:
    operation = queue["tasks"][0]["operations"][0]
    if product is None:
        operation.pop("product")
    else:
        operation["product"] = product
    _write_queue(queue)
    with pytest.raises(session.WorkflowError, match="requires known product"):
        session.load_tasks()


@pytest.mark.parametrize("task_index", [0, 1])
def test_each_product_requires_every_operation_owner(
    queue: dict[str, Any], task_index: int
) -> None:
    product = queue["tasks"][task_index]["operations"].pop()["product"]
    _write_queue(queue)
    with pytest.raises(session.WorkflowError, match=f"{product.capitalize()} operations missing"):
        session.load_tasks()


@pytest.mark.parametrize("task_index", [0, 1])
def test_each_product_rejects_duplicate_owner(queue: dict[str, Any], task_index: int) -> None:
    duplicate = deepcopy(queue["tasks"][task_index]["operations"][0])
    queue["tasks"][2]["operations"].append(duplicate)
    _write_queue(queue)
    with pytest.raises(session.WorkflowError, match="Duplicate operation ownership"):
        session.load_tasks()


@pytest.mark.parametrize("task_index", [0, 1])
def test_operations_cannot_use_other_products_paths(queue: dict[str, Any], task_index: int) -> None:
    operation = queue["tasks"][task_index]["operations"][0]
    operation["path"] = "/markets" if task_index == 0 else "/pay/0"
    _write_queue(queue)
    with pytest.raises(session.WorkflowError, match=f"absent from {operation['product']} snapshot"):
        session.load_tasks()


@pytest.mark.parametrize("field,value", [("method", None), ("path", []), ("method", "get")])
def test_malformed_operation_is_rejected(queue: dict[str, Any], field: str, value: Any) -> None:
    queue["tasks"][1]["operations"][0][field] = value
    _write_queue(queue)
    with pytest.raises(session.WorkflowError, match="method/path|absent from exchange"):
        session.load_tasks()


def test_missing_exchange_snapshot_does_not_reuse_pay(queue: dict[str, Any]) -> None:
    (session.ROOT / "spec/openapi/exchange-current.json").unlink()
    with pytest.raises(session.WorkflowError, match="Missing exchange snapshot"):
        session.load_tasks()


@pytest.mark.parametrize("change", ["remove", "add"])
def test_pay_inventory_stays_exactly_25(queue: dict[str, Any], change: str) -> None:
    snapshot_path = session.ROOT / "spec/openapi/pay-current.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if change == "remove":
        snapshot["paths"].pop("/pay/0")
        queue["tasks"][0]["operations"].pop(1)
    else:
        snapshot["paths"]["/extra"] = {"get": {}}
        queue["tasks"][0]["operations"].append(
            {"product": "pay", "method": "GET", "path": "/extra"}
        )
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    _write_queue(queue)
    with pytest.raises(session.WorkflowError, match="Pay snapshot must contain 25 operations"):
        session.load_tasks()


@pytest.mark.parametrize("paths", [None, {}, {"/markets": "invalid"}, {"markets": {"get": {}}}])
def test_invalid_exchange_snapshot_cannot_silently_drop_inventory(
    queue: dict[str, Any], paths: Any
) -> None:
    (session.ROOT / "spec/openapi/exchange-current.json").write_text(
        json.dumps({"paths": paths}), encoding="utf-8"
    )
    with pytest.raises(session.WorkflowError, match="paths|path item|No REST operations"):
        session.load_tasks()


def test_queue_v1_does_not_infer_product(queue: dict[str, Any]) -> None:
    queue["version"] = 1
    _write_queue(queue)
    with pytest.raises(session.WorkflowError, match="Unknown queue version"):
        session.load_tasks()


@pytest.mark.parametrize(
    "mutation,message",
    [
        ("cycle", "Dependency cycle"),
        ("unknown_dependency", "Unknown dependency"),
        ("unfinished_dependency", "dependencies must be done"),
        ("two_active", "Only one task can be in_progress"),
        ("missing_card", "Missing file"),
        ("escaping_card", "Path escapes workflow"),
        ("wrong_handoff", "Handoff must belong"),
        ("done_without_handoff", "done/blocked requires"),
    ],
)
def test_queue_safeguards_remain_enforced(
    queue: dict[str, Any], mutation: str, message: str
) -> None:
    tasks = queue["tasks"]
    if mutation == "cycle":
        tasks[1]["depends_on"] = ["XLATER"]
    elif mutation == "unknown_dependency":
        tasks[1]["depends_on"] = ["UNKNOWN"]
    elif mutation == "unfinished_dependency":
        tasks[2]["status"] = "in_progress"
    elif mutation == "two_active":
        tasks[1]["status"] = tasks[2]["status"] = "in_progress"
    elif mutation == "missing_card":
        tasks[1]["card"] = "tasks/missing.md"
    elif mutation == "escaping_card":
        tasks[1]["card"] = "../outside.md"
    elif mutation == "wrong_handoff":
        tasks[1]["handoff"] = "handoffs/PAY-01.md"
    else:
        tasks[1]["status"] = "done"
    _write_queue(queue)
    with pytest.raises(session.WorkflowError, match=message):
        session.load_tasks()


@pytest.mark.parametrize(
    "task_id,active,message",
    [
        ("PAY", False, "is done"),
        ("XLATER", False, "Dependencies of XLATER are not done"),
        ("XLATER", True, "Another task is in_progress"),
    ],
)
def test_prompt_cannot_start_ineligible_task(
    queue: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    task_id: str,
    active: bool,
    message: str,
) -> None:
    if active:
        queue["tasks"][1]["status"] = "in_progress"
        _write_queue(queue)
    monkeypatch.setattr("sys.argv", ["session.py", "prompt", task_id])
    assert session.main() == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize("command", ["next", "prompt", "review"])
def test_prompts_preserve_single_task_and_review_boundaries(
    queue: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    args = ["session.py", command]
    if command != "next":
        args.append("XPUBLIC" if command == "prompt" else "PAY")
    monkeypatch.setattr("sys.argv", args)
    assert session.main() == 0
    output = capsys.readouterr().out
    if command == "review":
        assert "read-only review" in output
        assert "Не меняй файлы и статусы" in output
    else:
        assert "Выполни только XPUBLIC" in output
        assert "следующий ID, без его исполнения" in output
        assert "Handoff зависимости PAY:" in output
