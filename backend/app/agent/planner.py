from __future__ import annotations

import json
from typing import Any, Callable

from app.db import repository as repo
from app.llm.base import BaseLLM
from app.schemas.models import PlanOutput
from app.tools import get_tool, tool_catalog

from .prompts import PLANNER_SYSTEM, planner_user
from .state import AgentState
from .status import RunStatus


def _normalize_step_ids(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    for index, step in enumerate(steps, start=1):
        step_id = str(step.get("step_id") or f"s{index}").strip()
        if step_id in seen:
            raise ValueError(f"计划中存在重复的 step_id：{step_id}")
        seen.add(step_id)
        step["step_id"] = step_id
    return steps


def make_planner_node(llm: BaseLLM) -> Callable[[AgentState], dict[str, Any]]:
    def planner_node(state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        question = state["question"]
        feedback = state.get("manager_feedback")
        attempts = int(state.get("plan_attempts", 0))
        max_attempts = int(state.get("max_plan_attempts", 3))

        if feedback and attempts >= max_attempts:
            error = f"计划连续被驳回，已达到最大修改次数（{max_attempts}）"
            repo.update_run(run_id, status=RunStatus.FAILED, error=error)
            repo.add_event(run_id, "plan.failed", {"error": error})
            return {"status": RunStatus.FAILED, "error": error}

        repo.update_run(run_id, status=RunStatus.PLANNING)
        repo.add_event(
            run_id,
            "plan.started",
            {"attempt": attempts + 1, "feedback": feedback},
        )

        try:
            output: PlanOutput = llm.complete_structured(
                PLANNER_SYSTEM,
                planner_user(
                    question,
                    tool_catalog(),
                    feedback=feedback,
                    attempt=attempts + 1,
                ),
                PlanOutput,
            )
            steps = _normalize_step_ids([step.model_dump() for step in output.steps])
            for step in steps:
                get_tool(step["tool_name"])  # validate tool name early
        except Exception as exc:  # noqa: BLE001
            error = f"规划失败：{type(exc).__name__}: {exc}"
            repo.update_run(run_id, status=RunStatus.FAILED, error=error)
            repo.add_event(run_id, "plan.failed", {"error": error})
            return {"status": RunStatus.FAILED, "error": error}

        repo.replace_steps(run_id, steps, start_index=0)
        repo.update_run(
            run_id,
            status=RunStatus.WAITING_APPROVAL,
            plan_json=json.dumps(steps, ensure_ascii=False),
            error=None,
        )
        repo.add_event(
            run_id,
            "plan.generated",
            {
                "plan": steps,
                "reasoning": output.reasoning,
                "attempt": attempts + 1,
            },
        )
        return {
            "plan": steps,
            "status": RunStatus.WAITING_APPROVAL,
            "cursor": 0,
            "observations": {},
            "manager_feedback": None,
            "plan_attempts": attempts + 1,
            "replan_count": 0,
            "last_error": None,
            "error": None,
            "final_answer": None,
        }

    return planner_node
