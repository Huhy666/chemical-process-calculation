from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from app.config import Settings, settings
from app.db import repository as repo
from app.llm.base import BaseLLM
from app.llm.factory import build_llm

from .executor import make_executor_node
from .finalizer import make_finalizer_node
from .planner import make_planner_node
from .replanner import make_replanner_node
from .state import AgentState
from .status import RunStatus


def approval_node(state: AgentState) -> dict[str, Any]:
    run_id = state["run_id"]
    repo.update_run(run_id, status=RunStatus.WAITING_APPROVAL)
    decision = interrupt(
        {
            "type": "plan_approval",
            "run_id": run_id,
            "question": state["question"],
            "plan": state.get("plan", []),
        }
    )
    decision = decision or {}
    action = decision.get("action", "approve")

    if action == "approve":
        repo.update_run(run_id, status=RunStatus.EXECUTING)
        repo.add_event(run_id, "plan.approved", {})
        return {"status": RunStatus.EXECUTING, "manager_feedback": None}

    feedback = decision.get("feedback") or "请调整计划"
    repo.update_run(run_id, status=RunStatus.PLANNING)
    repo.add_event(run_id, "plan.rejected", {"feedback": feedback})
    return {"status": RunStatus.PLANNING, "manager_feedback": feedback}


def _after_planner(state: AgentState) -> str:
    return "end" if state.get("status") == RunStatus.FAILED else "approval"


def _after_approval(state: AgentState) -> str:
    return "plan" if state.get("status") == RunStatus.PLANNING else "execute"


def _after_executor(state: AgentState) -> str:
    if state.get("status") == RunStatus.REPLANNING:
        return "replan"
    if int(state.get("cursor", 0)) >= len(state.get("plan", [])):
        return "done"
    return "continue"


def _after_replanner(state: AgentState) -> str:
    return "end" if state.get("status") == RunStatus.FAILED else "execute"


def build_graph(llm: BaseLLM, checkpointer: SqliteSaver) -> Any:
    graph = StateGraph(AgentState)
    graph.add_node("planner", make_planner_node(llm))
    graph.add_node("approval", approval_node)
    graph.add_node("executor", make_executor_node())
    graph.add_node("replanner", make_replanner_node(llm))
    graph.add_node("finalizer", make_finalizer_node(llm))

    graph.set_entry_point("planner")
    graph.add_conditional_edges(
        "planner", _after_planner, {"approval": "approval", "end": "finalizer"}
    )
    graph.add_conditional_edges(
        "approval", _after_approval, {"plan": "planner", "execute": "executor"}
    )
    graph.add_conditional_edges(
        "executor",
        _after_executor,
        {"continue": "executor", "replan": "replanner", "done": "finalizer"},
    )
    graph.add_conditional_edges(
        "replanner", _after_replanner, {"execute": "executor", "end": "finalizer"}
    )
    graph.add_edge("finalizer", END)
    return graph.compile(checkpointer=checkpointer)


def _initial_state(
    run_id: str, question: str, max_replans: int, max_plan_attempts: int
) -> AgentState:
    return {
        "run_id": run_id,
        "question": question,
        "plan": [],
        "manager_feedback": None,
        "cursor": 0,
        "observations": {},
        "replan_count": 0,
        "max_replans": max_replans,
        "plan_attempts": 0,
        "max_plan_attempts": max_plan_attempts,
        "status": RunStatus.CREATED,
        "last_error": None,
        "final_answer": None,
        "error": None,
    }


@dataclass
class AgentRuntime:
    llm: BaseLLM
    checkpointer: SqliteSaver
    graph: Any
    max_replans: int = 2
    max_plan_attempts: int = 3
    lock: threading.RLock = field(default_factory=threading.RLock)

    def start(self, run_id: str, question: str) -> None:
        self._invoke(
            run_id,
            _initial_state(
                run_id,
                question,
                self.max_replans,
                self.max_plan_attempts,
            ),
        )

    def resume(self, run_id: str, decision: dict[str, Any]) -> None:
        self._invoke(run_id, Command(resume=decision))

    def _invoke(self, run_id: str, payload: Any) -> None:
        config = {"configurable": {"thread_id": run_id}}
        try:
            with self.lock:
                self.graph.invoke(payload, config=config)
        except Exception as exc:  # noqa: BLE001 - background task must never crash silently
            error = f"Agent 运行异常：{type(exc).__name__}: {exc}"
            answer = f"## 执行失败\n\n{error}"
            repo.update_run(
                run_id,
                status=RunStatus.FAILED,
                error=error,
                final_answer=answer,
            )
            repo.add_event(run_id, "run.failed", {"error": error})

    def close(self) -> None:
        conn = getattr(self.checkpointer, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def build_runtime(
    cfg: Settings | None = None, llm: BaseLLM | None = None
) -> AgentRuntime:
    config = cfg or settings
    llm = llm or build_llm(config)

    checkpoint_path = Path(config.checkpoint_db_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(checkpoint_path), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()

    graph = build_graph(llm, saver)
    return AgentRuntime(
        llm=llm,
        checkpointer=saver,
        graph=graph,
        max_replans=config.max_replans,
        max_plan_attempts=config.max_plan_attempts,
    )
