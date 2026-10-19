from __future__ import annotations

import json
from typing import Any

PLANNER_SYSTEM = """你是一名资深化工工艺工程师，负责把用户的化工计算问题拆解为可执行的计算计划。

规则：
1. 只能使用“可用工具”中列出的工具，tool_name 必须与工具名完全一致。
2. 计划包含 1~8 步，按执行顺序排列，step_id 依次为 s1、s2、s3……
3. 每一步只调用一个工具；tool_args 必须符合该工具的 input_schema。
4. 如果某个参数依赖前序步骤的结果，把整个参数值写成字符串 "${步骤ID.字段名}"，
   例如 "${s1.density_kg_m3}"。引用只能指向排在前面的步骤。
5. 不要编造物性数据；需要物性时先用 get_substance_properties 查询。
6. 参数中的数值直接写数字，不要带单位；单位由各工具约定。
7. 尽量给出最少、最可靠的计算步骤，不要添加“解释结果”之类的步骤。
8. 你只负责制定计划，不执行计算。"""


def planner_user(
    question: str,
    catalog: list[dict[str, Any]],
    feedback: str | None = None,
    attempt: int = 1,
) -> str:
    feedback_block = ""
    if feedback:
        feedback_block = (
            f"\n上一版计划被审核人驳回，驳回意见：{feedback}\n"
            "请根据驳回意见调整计划，仍然只输出完整的新计划。\n"
        )
    return (
        f"用户问题：\n{question}\n\n"
        f"可用工具（JSON 目录）：\n{json.dumps(catalog, ensure_ascii=False, indent=2)}\n\n"
        f"当前是第 {attempt} 次规划。\n{feedback_block}"
    )


REPLANNER_SYSTEM = """你是一名资深化工工艺工程师，负责在步骤执行失败后修复计划。

你需要判断：
- 如果能通过调整剩余步骤继续完成用户目标，返回新的 remaining_steps；
- 如果无法继续，返回 give_up=true 并说明原因。

规则：
1. 只能使用“可用工具”中列出的工具。
2. remaining_steps 会替换从失败步骤开始的所有剩余步骤，已完成步骤不会重跑。
3. 新步骤的 step_id 必须接续已有编号（例如已完成 s1、s2，则从 s3 开始），且不能重复。
4. 依赖已完成步骤结果时，仍然使用 "${步骤ID.字段名}" 引用。
5. 不要重复已经成功的计​算步骤。"""


def replanner_user(
    question: str,
    plan: list[dict[str, Any]],
    cursor: int,
    observations: dict[str, Any],
    failure: str | None,
    catalog: list[dict[str, Any]],
) -> str:
    completed = [step["step_id"] for step in plan[:cursor]]
    failed = plan[cursor]["step_id"] if cursor < len(plan) else "无"
    return (
        f"用户问题：\n{question}\n\n"
        f"当前计划：\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        f"已完成步骤编号：{completed}\n"
        f"已完成步骤结果 JSON：\n{json.dumps(observations, ensure_ascii=False, indent=2)}\n\n"
        f"失败步骤：{failed}\n"
        f"失败原因：{failure}\n\n"
        f"可用工具（JSON 目录）：\n{json.dumps(catalog, ensure_ascii=False, indent=2)}"
    )


FINALIZER_SYSTEM = """你是一名资深化工工艺工程师，负责撰写最终报告（最终计算报告）。

规则：
1. 只能使用“步骤结果 JSON”中出现的数值，不得自行编造或外推数据。
2. 报告使用中文 Markdown，包含：计算结论、关键中间结果、采用的计算方法、假设与注意事项。
3. 引用结果时标注步骤编号，例如“由 s2 得到换热量 3483 kW”。
4. 如果提供了错误信息，必须在报告开头说明哪些步骤失败、结论是否完整。
5. 数值保留合理有效数字并带单位。
6. 不要输出与计算无关的客套话。"""


def finalizer_user(
    question: str,
    plan: list[dict[str, Any]],
    observations: dict[str, Any],
    error: str | None,
) -> str:
    payload = {
        "question": question,
        "plan": plan,
        "observations": observations,
        "error": error,
    }
    return (
        f"用户问题：\n{question}\n\n"
        f"步骤结果 JSON：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
