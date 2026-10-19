from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    question: str
    plan: list[dict[str, Any]]
    manager_feedback: str | None
    cursor: int
    observations: dict[str, dict[str, Any]]
    replan_count: int
    max_replans: int
    plan_attempts: int
    max_plan_attempts: int
    status: str
    last_error: str | None
    final_answer: str | None
    error: str | None
