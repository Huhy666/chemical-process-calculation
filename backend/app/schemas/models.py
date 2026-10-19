from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    step_id: str = Field(description="步骤编号，必须为 s1、s2、s3…，在本计划内唯一")
    title: str = Field(description="步骤标题，不超过 20 字")
    description: str = Field(description="这一步计算什么、为什么需要")
    tool_name: str = Field(description="必须来自工具目录中的工具名")
    tool_args: dict[str, Any] = Field(
        default_factory=dict,
        description="工具参数；依赖前序结果时使用 ${步骤ID.字段名} 引用",
    )
    expected_output: str = Field(default="", description="这一步预期得到的关键结果")


class PlanOutput(BaseModel):
    reasoning: str = Field(default="", description="简要说明计划思路")
    steps: list[PlanStep] = Field(min_length=1, max_length=8)


class ReplanOutput(BaseModel):
    give_up: bool = Field(default=False, description="是否放弃继续执行")
    reason: str = Field(default="", description="重规划原因或放弃原因")
    remaining_steps: list[PlanStep] = Field(
        default_factory=list,
        description="替换剩余步骤的新步骤列表，编号应接续当前的 sN",
    )


class CreateRunRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class ApprovalRequest(BaseModel):
    action: Literal["approve", "reject"]
    feedback: str | None = Field(default=None, max_length=1000)


class ApprovalDecision(BaseModel):
    action: Literal["approve", "reject"]
    feedback: str | None = None
