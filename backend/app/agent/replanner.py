from __future__ import annotations

import json
from typing import Any, Callable

from app.db import repository as repo
from app.llm.base import BaseLLM
from app.schemas.models import ReplanOutput
from app.tools import get_tool, tool_catalog

from .prompts import REPLANNER_SYSTEM, replanner_user
from .state import AgentState
from .status import RunStatus


def _validate_replacement_steps(
    state: AgentState, steps: list[dict[str, Any]]
) -> None:
    cursor = int(state.get("cursor", 0))
    plan = state.get("plan", [])
    completed_ids = {step["step_id"] for step in plan[:cursor]}
    seen: set[str] = set()
    for step in steps:
        step_id = str(step.get("step_id", "")).strip()
        if not step_id:
            raise ValueError("重规划步骤缺少 step_id")
        if step_id in seen or step_id in completed_ids:
            raise ValueError(f"重规划步骤 step_id 冲突：{step_id}")
        seen.add(step_id)
        get_tool(step["tool_name"])


def make_replanner_node(llm: BaseLLM) -> Callable[[AgentState], dict[str, Any]]:
    def replanner_node(state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        cursor = int(state.get("cursor", 0))
        plan = state.get("plan", [])
        failure = state.get("last_error")
        replan_count = int(state.get("replan_count", 0))
        max_replans = int(state.get("max_replans", 2))

        repo.update_run(run_id, status=RunStatus.REPLANNING)
        repo.add_event(
            run_id,
            "replan.started",
            {
                "replan_count": replan_count + 1,
                "failed_step": plan[cursor]["step_id"] if cursor < len(plan) else None,
                "error": failure,
            },
        )

        if replan_count >= max_replans:
            error = f"步骤失败且自动重规划次数已达上限（{max_replans}）：{failure}"
            repo.update_run(run_id, status=RunStatus.FAILED, error=error)
            repo.add_event(run_id, "replan.exhausted", {"error": error})
            return {"status": RunStatus.FAILED, "error": error}

        try:
            output: ReplanOutput = llm.complete_structured(
                REPLANNER_SYSTEM,
                replanner_user(
                    state["question"],
                    plan,
                    cursor,
                    state.get("observations", {}),
                    failure,
                    tool_catalog(),
                ),
                ReplanOutput,
            )
        except Exception as exc:  # noqa: BLE001
            error = f"重规划失败：{type(exc).__name__}: {exc}"
            repo.update_run(run_id, status=RunStatus.FAILED, error=error)
            repo.add_event(run_id, "replan.failed", {"error": error})
            return {"status": RunStatus.FAILED, "error": error}

        if output.give_up or not output.remaining_steps:
            error = f"无法继续执行：{output.reason or failure or '重规划器选择放弃'}"
            repo.update_run(run_id, status=RunStatus.FAILED, error=error)
            repo.add_event(run_id, "replan.gave_up", {"error": error})
            return {"status": RunStatus.FAILED, "error": error}

        try:
            new_steps = [step.model_dump() for step in output.remaining_steps]
            _validate_replacement_steps(state, new_steps)
        except Exception as exc:  # noqa: BLE001
            error = f"重规划结果无效：{exc}"
            repo.update_run(run_id, status=RunStatus.FAILED, error=error)
            repo.add_event(run_id, "replan.failed", {"error": error})
            return {"status": RunStatus.FAILED, "error": error}

        new_plan = plan[:cursor] + new_steps
        repo.replace_steps(run_id, new_steps, start_index=cursor)
        repo.update_run(
            run_id,
            status=RunStatus.EXECUTING,
            plan_json=json.dumps(new_plan, ensure_ascii=False),
            replan_count=replan_count + 1,
            error=None,
        )
        repo.add_event(
            run_id,
            "replan.generated",
            {
                "reason": output.reason,
                "remaining_steps": new_steps,
                "plan": new_plan,
                "replan_count": replan_count + 1,
            },
        )
        return {
            "plan": new_plan,
            "replan_count": replan_count + 1,
            "last_error": None,
            "status": RunStatus.EXECUTING,
            "error": None,
        }

    return replanner_node
