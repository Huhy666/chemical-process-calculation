from __future__ import annotations

import json
from typing import Any, Callable

from app.db import repository as repo
from app.llm.base import BaseLLM

from .prompts import FINALIZER_SYSTEM, finalizer_user
from .state import AgentState
from .status import RunStatus


def _fallback_report(state: AgentState, error: str | None) -> str:
    observations = state.get("observations", {})
    plan = {step["step_id"]: step for step in state.get("plan", [])}
    lines = ["## 计算结果", ""]
    if error:
        lines.extend([f"> 执行中断：{error}", ""])
    if not observations:
        lines.append("没有产生任何计算结果。")
        return "\n".join(lines)
    for index, (step_id, result) in enumerate(observations.items(), start=1):
        title = plan.get(step_id, {}).get("title", step_id)
        lines.append(f"### {index}. {title}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(result, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def make_finalizer_node(llm: BaseLLM) -> Callable[[AgentState], dict[str, Any]]:
    def finalizer_node(state: AgentState) -> dict[str, Any]:
        run_id = state["run_id"]
        error = state.get("error") or state.get("last_error")
        observations = state.get("observations", {})
        current_status = state.get("status")

        if current_status == RunStatus.FAILED and not observations:
            answer = f"## 执行失败\n\n{error or '未知错误'}"
            repo.update_run(
                run_id,
                status=RunStatus.FAILED,
                final_answer=answer,
                error=error,
            )
            repo.add_event(run_id, "run.failed", {"error": error, "final_answer": answer})
            return {"final_answer": answer, "status": RunStatus.FAILED}

        try:
            answer = llm.complete_text(
                FINALIZER_SYSTEM,
                finalizer_user(
                    state["question"],
                    state.get("plan", []),
                    observations,
                    error,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            answer = _fallback_report(state, error)
            if not error:
                answer = (
                    f"> 自动报告生成失败（{type(exc).__name__}），以下为结构化结果。\n\n"
                    + answer
                )

        final_status = RunStatus.FAILED if error else RunStatus.COMPLETED
        repo.update_run(
            run_id,
            status=final_status,
            final_answer=answer,
            error=error,
        )
        repo.add_event(
            run_id,
            "run.completed" if final_status == RunStatus.COMPLETED else "run.failed",
            {"final_answer": answer, "error": error},
        )
        return {"final_answer": answer, "status": final_status}

    return finalizer_node
