from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .engine import db

RUN_UPDATABLE = {"status", "plan_json", "final_answer", "error", "replan_count"}
STEP_UPDATABLE = {
    "status",
    "result_json",
    "error",
    "started_at",
    "finished_at",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(value: str | None) -> Any:
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _run_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "question": row["question"],
        "status": row["status"],
        "plan": _loads(row["plan_json"]),
        "final_answer": row["final_answer"],
        "error": row["error"],
        "replan_count": row["replan_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _step_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "step_index": row["step_index"],
        "step_id": row["step_id"],
        "title": row["title"],
        "description": row["description"],
        "tool_name": row["tool_name"],
        "tool_args": _loads(row["tool_args_json"]) or {},
        "expected_output": row["expected_output"],
        "status": row["status"],
        "result": _loads(row["result_json"]),
        "error": row["error"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


def _event_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "type": row["type"],
        "payload": _loads(row["payload_json"]),
        "created_at": row["created_at"],
    }


def create_run(run_id: str, question: str, status: str = "CREATED") -> dict[str, Any]:
    timestamp = now()
    with db() as conn:
        conn.execute(
            "INSERT INTO runs (id, question, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, question, status, timestamp, timestamp),
        )
    return get_run(run_id)  # type: ignore[return-value]


def get_run(run_id: str) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _run_row(row) if row else None


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_run_row(row) for row in rows]


def update_run(run_id: str, **fields: Any) -> None:
    unknown = set(fields) - RUN_UPDATABLE
    if unknown:
        raise ValueError(f"非法 runs 字段：{unknown}")
    if not fields:
        return
    fields["updated_at"] = now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [run_id]
    with db() as conn:
        conn.execute(f"UPDATE runs SET {assignments} WHERE id = ?", values)


def replace_steps(run_id: str, steps: list[dict[str, Any]], start_index: int = 0) -> None:
    with db() as conn:
        conn.execute(
            "DELETE FROM steps WHERE run_id = ? AND step_index >= ?",
            (run_id, start_index),
        )
        for offset, step in enumerate(steps):
            conn.execute(
                "INSERT INTO steps ("
                "id, run_id, step_index, step_id, title, description, tool_name, "
                "tool_args_json, expected_output, status"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    run_id,
                    start_index + offset,
                    step["step_id"],
                    step.get("title", ""),
                    step.get("description", ""),
                    step.get("tool_name", ""),
                    json.dumps(step.get("tool_args", {}), ensure_ascii=False),
                    step.get("expected_output", ""),
                    "pending",
                ),
            )


def update_step(run_id: str, step_index: int, **fields: Any) -> None:
    unknown = set(fields) - STEP_UPDATABLE
    if unknown:
        raise ValueError(f"非法 steps 字段：{unknown}")
    if not fields:
        return
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [run_id, step_index]
    with db() as conn:
        conn.execute(
            f"UPDATE steps SET {assignments} WHERE run_id = ? AND step_index = ?",
            values,
        )


def get_steps(run_id: str) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM steps WHERE run_id = ? ORDER BY step_index", (run_id,)
        ).fetchall()
    return [_step_row(row) for row in rows]


def add_event(run_id: str, event_type: str, payload: Any = None) -> int:
    timestamp = now()
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO events (run_id, type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (
                run_id,
                event_type,
                json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                timestamp,
            ),
        )
        return int(cursor.lastrowid)


def get_events(run_id: str, after_id: int = 0, limit: int = 500) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id LIMIT ?",
            (run_id, after_id, limit),
        ).fetchall()
    return [_event_row(row) for row in rows]


def get_run_detail(run_id: str, after_event_id: int = 0) -> dict[str, Any] | None:
    run = get_run(run_id)
    if run is None:
        return None
    return {
        "run": run,
        "steps": get_steps(run_id),
        "events": get_events(run_id, after_event_id),
    }
