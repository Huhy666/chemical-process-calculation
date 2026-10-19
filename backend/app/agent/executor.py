from __future__ import annotations

import json
from typing import Any, Callable

from app.db import repository as repo
from app.tools import RefResolutionError, ToolError, get_tool

from .refs import resolve_refs
from .state import AgentState
from .status import RunStatus


def make_executor_node() -> Callable[[AgentState], dict[str, Any]]:
    def executor_node(state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        plan = state.get("plan", [])
        cursor = int(state.get("cursor", 0))

        if cursor >= len(plan):
            return {"status": RunStatus.EXECUTING}

        step = plan[cursor]
        step_id = step["step_id"]
        tool_name = step["tool_name"]

        repo.update_run(run_id, status=RunStatus.EXECUTING)
        repo.update_step(
            run_id,
            cursor,
            status="running",
            started_at=repo.now(),
            error=None,
        )
        repo.add_event(
            run_id,
            "step.started",
            {
                "index": cursor,
                "step_id": step_id,
                "title": step.get("title", ""),
                "tool_name": tool_name,
            },
        )

        try:
            resolved_args = resolve_refs(step.get("tool_args", {}), state.get("observations", {}))
            tool = get_tool(tool_name)
            result = tool.run(resolved_args)
        except (ToolError, RefResolutionError) as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
        else:
            observations = dict(state.get("observations", {}))
            observations[step_id] = result
            repo.update_step(
                run_id,
                cursor,
                status="succeeded",
                result_json=json.dumps(result, ensure_ascii=False),
                finished_at=repo.now(),
            )
            repo.add_event(
                run_id,
                "step.succeeded",
                {"index": cursor, "step_id": step_id, "result": result},
            )
            return {
                "cursor": cursor + 1,
                "observations": observations,
                "last_error": None,
                "status": RunStatus.EXECUTING,
            }

        repo.update_step(
            run_id,
            cursor,
            status="failed",
            error=error,
            finished_at=repo.now(),
        )
        repo.add_event(
            run_id,
            "step.failed",
            {"index": cursor, "step_id": step_id, "error": error},
        )
        return {
            "last_error": error,
            "status": RunStatus.REPLANNING,
        }

    return executor_node
