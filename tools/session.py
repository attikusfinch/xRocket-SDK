"""Read-only queue validation and session prompts; Python 3.11+, standard library."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "workflow"
STATUSES = {"todo", "in_progress", "blocked", "done"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
SNAPSHOT_FILES = {"pay": "pay-current.json", "exchange": "exchange-current.json"}


class WorkflowError(Exception):
    """Invalid or inconsistent local workflow files."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowError(message)


def workflow_file(value: Any) -> Path:
    require(isinstance(value, str) and bool(value), "Expected a nonempty workflow path")
    path = (WORKFLOW / cast(str, value)).resolve()
    require(path.is_relative_to(WORKFLOW.resolve()), f"Path escapes workflow: {value}")
    require(path.is_file(), f"Missing file: {path}")
    require(bool(path.read_text(encoding="utf-8-sig").strip()), f"Empty file: {path}")
    return path


def snapshot_operations() -> dict[str, set[tuple[str, str]]]:
    """Read each product's REST inventory from its fixed, independent snapshot."""
    inventories: dict[str, set[tuple[str, str]]] = {}
    for product, filename in SNAPSHOT_FILES.items():
        snapshot = ROOT / "spec" / "openapi" / filename
        require(snapshot.is_file(), f"Missing {product} snapshot: {snapshot}")
        schema = json.loads(snapshot.read_text(encoding="utf-8"))
        require(isinstance(schema, dict), f"Invalid {product} snapshot document")
        paths = schema.get("paths")
        require(isinstance(paths, dict), f"Invalid paths in {product} snapshot")
        operations: set[tuple[str, str]] = set()
        for path, item in paths.items():
            require(
                isinstance(path, str) and path.startswith("/") and isinstance(item, dict),
                f"Invalid path item in {product} snapshot: {path}",
            )
            operations.update((method.upper(), path) for method in item if method in HTTP_METHODS)
        require(bool(operations), f"No REST operations in {product} snapshot")
        if product == "pay":
            require(
                len(operations) == 25,
                f"Pay snapshot must contain 25 operations: {len(operations)}",
            )
        inventories[product] = operations
    return inventories


def load_tasks() -> list[dict[str, Any]]:
    document = json.loads((WORKFLOW / "tasks.json").read_text(encoding="utf-8-sig"))
    require(isinstance(document, dict) and document.get("version") == 2, "Unknown queue version")
    tasks = document.get("tasks")
    require(isinstance(tasks, list) and bool(tasks), "tasks must be a nonempty array")
    by_id: dict[str, dict[str, Any]] = {}
    for task in tasks:
        require(isinstance(task, dict), "Each task must be an object")
        task_id = task.get("id")
        require(
            isinstance(task_id, str) and bool(re.fullmatch(r"[A-Z][A-Z0-9_-]*", task_id)),
            f"Invalid task ID: {task_id}",
        )
        require(task_id not in by_id, f"Duplicate task ID: {task_id}")
        require(
            isinstance(task.get("title"), str) and bool(task["title"].strip()),
            f"Missing title: {task_id}",
        )
        require(task.get("status") in STATUSES, f"Invalid status: {task_id}")
        dependencies = task.get("depends_on")
        require(
            isinstance(dependencies, list) and all(isinstance(d, str) for d in dependencies),
            f"Invalid dependencies: {task_id}",
        )
        require(len(dependencies) == len(set(dependencies)), f"Duplicate dependencies: {task_id}")
        workflow_file(task.get("card"))
        require("handoff" in task, f"Missing handoff field: {task_id}")
        if task["handoff"] is not None:
            handoff = workflow_file(task["handoff"])
            require(
                bool(re.fullmatch(re.escape(task_id) + r"-\d+\.md", handoff.name)),
                f"Handoff must belong to {task_id}: {handoff.name}",
            )
        require(
            task["status"] not in {"done", "blocked"} or task["handoff"] is not None,
            f"{task_id}: done/blocked requires an existing handoff",
        )
        require(isinstance(task.get("operations"), list), f"Missing operations array: {task_id}")
        by_id[task_id] = task

    require(
        sum(t["status"] == "in_progress" for t in tasks) <= 1,
        "Only one task can be in_progress in this checkout",
    )
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(task_id: str) -> None:
        require(task_id not in visiting, f"Dependency cycle at {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id]["depends_on"]:
            require(dependency in by_id, f"Unknown dependency {dependency} in {task_id}")
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id, task in by_id.items():
        visit(task_id)
        if task["status"] in {"done", "in_progress"}:
            require(
                all(by_id[d]["status"] == "done" for d in task["depends_on"]),
                f"{task_id}: dependencies must be done before starting/completing",
            )

    inventories = snapshot_operations()
    owners: dict[tuple[str, str, str], str] = {}
    for task in tasks:
        for operation in task["operations"]:
            require(isinstance(operation, dict), f"Invalid operation in {task['id']}")
            product = operation.get("product")
            require(
                isinstance(product, str) and product in SNAPSHOT_FILES,
                f"Operation requires known product (pay/exchange): {task['id']}",
            )
            method, path = operation.get("method"), operation.get("path")
            require(
                isinstance(method, str) and isinstance(path, str),
                f"Operation requires method/path: {task['id']}",
            )
            key = (product, method, path)
            require(
                (method, path) in inventories[product],
                f"Operation absent from {product} snapshot: {key}",
            )
            require(key not in owners, f"Duplicate operation ownership: {key}")
            owners[key] = task["id"]
    for product, expected in inventories.items():
        covered = {
            (method, path) for owner_product, method, path in owners if owner_product == product
        }
        require(
            covered == expected,
            f"{product.capitalize()} operations missing from queue: {sorted(expected - covered)}",
        )
    return cast(list[dict[str, Any]], tasks)


def available(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    done = {task["id"] for task in tasks if task["status"] == "done"}
    return [task for task in tasks if task["status"] == "todo" and set(task["depends_on"]) <= done]


def print_prompt(
    task: dict[str, Any], tasks: list[dict[str, Any]], *, review: bool = False
) -> None:
    by_id = {item["id"]: item for item in tasks}
    print(f"Проект: {ROOT}\nЗадача: {task['id']} — {task['title']}\n")
    print(f"Прочитай {ROOT / 'AGENTS.md'}, workflow/STATE.md и workflow/DECISIONS.md.")
    print(f"Карточка: {workflow_file(task['card'])}")
    print("Статус и зависимости проверь по workflow/tasks.json и реальным файлам.")
    if task["handoff"]:
        print(f"Последний handoff задачи: {workflow_file(task['handoff'])}")
    for dependency in task["depends_on"]:
        handoff = by_id[dependency]["handoff"]
        if handoff:
            print(f"Handoff зависимости {dependency}: {workflow_file(handoff)}")
    if review:
        print("\nСделай read-only review выполнения этой карточки: контракт, acceptance, код,")
        print("tests, sync/async и регрессии. Дай конкретные findings с местом и сценарием.")
        print("Не меняй файлы и статусы; другую задачу не начинай. Укажи границы проверки.")
    else:
        verb = "Продолжи" if task["status"] == "in_progress" else "Выполни"
        print(f"\n{verb} только {task['id']} по общему протоколу, не весь roadmap.")
        print("Сохрани новый handoff, обнови tasks.json/STATE.md и существенные решения.")
        print("Выполни необходимые проверки и tools/session.py check. Не отмечай незавершённое")
        print("как done. Заверши сессию, назвав следующий ID, без его исполнения.")


def main() -> int:
    # Windows redirected output may use a legacy code page; prompts must stay copyable.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["next", "prompt", "review", "check"], nargs="?", default="next"
    )
    parser.add_argument("task_id", nargs="?")
    args = parser.parse_args()
    try:
        tasks = load_tasks()
        if args.command in {"prompt", "review"}:
            require(bool(args.task_id), f"{args.command} requires a task ID")
            task = next((t for t in tasks if t["id"] == args.task_id), None)
            if task is None:
                raise WorkflowError(f"Unknown task: {args.task_id}")
            if args.command == "prompt":
                require(
                    task["status"] in {"todo", "in_progress"},
                    f"{task['id']} is {task['status']}; review it or resolve its blocker first",
                )
                require(
                    not any(t["status"] == "in_progress" and t["id"] != task["id"] for t in tasks),
                    "Another task is in_progress; finish or hand it off before selecting this task",
                )
                require(
                    task["status"] == "in_progress" or task in available(tasks),
                    f"Dependencies of {task['id']} are not done",
                )
            print_prompt(task, tasks, review=args.command == "review")
        elif args.command == "check":
            counts = Counter(t["status"] for t in tasks)
            print(f"Queue OK: {len(tasks)} tasks; {dict(counts)}")
            operation_counts = Counter(
                operation["product"] for task in tasks for operation in task["operations"]
            )
            for product in SNAPSHOT_FILES:
                print(
                    f"{product.capitalize()} snapshot operations: {operation_counts[product]}, "
                    "all covered exactly once (planned coverage, not runtime support)."
                )
            print("Ready: " + (", ".join(t["id"] for t in available(tasks)) or "none"))
        else:
            active = next((t for t in tasks if t["status"] == "in_progress"), None)
            ready = available(tasks)
            if active:
                print(
                    "Продолжение незавершённой задачи. Предыдущая сессия должна быть закончена.\n"
                )
                print_prompt(active, tasks)
            elif ready:
                print_prompt(ready[0], tasks)
            else:
                print(
                    "Доступных задач нет. Проверь blocked/dependencies "
                    "или добавь следующую карточку."
                )
        return 0
    except (WorkflowError, OSError, ValueError, TypeError, KeyError) as error:
        print(f"Workflow error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
