from __future__ import annotations

import uuid

import pytest

from app.agent.graph import build_runtime
from app.db import repository as repo
from app.llm.mock import MockLLM
from app.schemas.models import PlanOutput, PlanStep, ReplanOutput

WATER_QUESTION = (
    "将 50 m³/h 的水从 20°C 加热到 80°C，热源为 120°C 饱和蒸汽，"
    "总传热系数 K=800 W/(m²·K)，求所需换热面积。"
)


def new_run(runtime, question: str = WATER_QUESTION) -> str:
    run_id = uuid.uuid4().hex
    repo.create_run(run_id, question)
    runtime.start(run_id, question)
    return run_id


def test_plan_then_approve_completes(runtime):
    run_id = new_run(runtime)
    run = repo.get_run(run_id)
    assert run is not None
    assert run["status"] == "WAITING_APPROVAL"
    assert len(run["plan"]) == 3

    runtime.resume(run_id, {"action": "approve"})
    run = repo.get_run(run_id)
    assert run is not None
    assert run["status"] == "COMPLETED"
    assert run["error"] is None
    assert "计算结果" in (run["final_answer"] or "")

    steps = repo.get_steps(run_id)
    assert [step["status"] for step in steps] == ["succeeded"] * 3
    event_types = [event["type"] for event in repo.get_events(run_id)]
    assert "plan.generated" in event_types
    assert "plan.approved" in event_types
    assert "run.completed" in event_types


def test_reject_triggers_replanning(runtime):
    run_id = new_run(runtime)
    runtime.resume(
        run_id, {"action": "reject", "feedback": "请补充安全裕量说明"}
    )
    run = repo.get_run(run_id)
    assert run is not None
    assert run["status"] == "WAITING_APPROVAL"
    event_types = [event["type"] for event in repo.get_events(run_id)]
    assert "plan.rejected" in event_types
    assert event_types.count("plan.generated") == 2

    runtime.resume(run_id, {"action": "approve"})
    assert repo.get_run(run_id)["status"] == "COMPLETED"


class FailingPlanLLM(MockLLM):
    def complete_structured(self, system, user, schema):
        if schema is PlanOutput:
            return PlanOutput(
                steps=[
                    PlanStep(
                        step_id="s1",
                        title="查询不存在的物质",
                        description="故意失败，用于验证错误处理链路。",
                        tool_name="get_substance_properties",
                        tool_args={"name": "不存在的神秘物质"},
                        expected_output="无",
                    )
                ]
            )
        if schema is ReplanOutput:
            return ReplanOutput(give_up=True, reason="测试中主动放弃")
        return super().complete_structured(system, user, schema)


def test_failed_step_ends_with_failed_status():
    runtime = build_runtime(llm=FailingPlanLLM())
    try:
        run_id = uuid.uuid4().hex
        repo.create_run(run_id, "测试失败链路")
        runtime.start(run_id, "测试失败链路")
        runtime.resume(run_id, {"action": "approve"})

        run = repo.get_run(run_id)
        assert run is not None
        assert run["status"] == "FAILED"
        assert "无法继续执行" in (run["error"] or "")
        steps = repo.get_steps(run_id)
        assert steps[0]["status"] == "failed"
        event_types = [event["type"] for event in repo.get_events(run_id)]
        assert "step.failed" in event_types
        assert "replan.gave_up" in event_types
    finally:
        runtime.close()
