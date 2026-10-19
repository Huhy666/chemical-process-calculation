from __future__ import annotations

from typing import Any

import streamlit as st

STEP_ICONS = {
    "pending": "⚪",
    "running": "⏳",
    "succeeded": "✅",
    "failed": "❌",
}

STEP_LABELS = {
    "pending": "待执行",
    "running": "执行中",
    "succeeded": "已完成",
    "failed": "失败",
}


def render_steps(steps: list[dict[str, Any]]) -> None:
    if not steps:
        return
    st.markdown("#### 执行时间线")
    for index, step in enumerate(steps, start=1):
        status = step.get("status", "pending")
        icon = STEP_ICONS.get(status, "⚪")
        label = STEP_LABELS.get(status, status)
        with st.container(border=True):
            left, right = st.columns([4, 1])
            with left:
                st.markdown(f"{icon} **{index}. {step.get('title', '')}**")
                st.caption(
                    f"{step.get('step_id', '')} · `{step.get('tool_name', '')}`"
                )
            with right:
                st.markdown(
                    f"<div style='text-align:right;color:#6b7280;font-size:0.8rem'>{label}</div>",
                    unsafe_allow_html=True,
                )
            if step.get("error"):
                st.error(step["error"])
            with st.expander("参数与结果"):
                st.json(
                    {
                        "tool_args": step.get("tool_args", {}),
                        "result": step.get("result"),
                    }
                )


EVENT_LABELS = {
    "run.created": "创建运行",
    "plan.started": "开始规划",
    "plan.generated": "生成计划",
    "plan.approved": "计划已批准",
    "plan.rejected": "计划被驳回",
    "plan.failed": "规划失败",
    "step.started": "步骤开始",
    "step.succeeded": "步骤成功",
    "step.failed": "步骤失败",
    "replan.started": "开始重规划",
    "replan.generated": "重规划完成",
    "replan.exhausted": "重规划次数用尽",
    "replan.gave_up": "重规划放弃",
    "replan.failed": "重规划失败",
    "run.completed": "运行完成",
    "run.failed": "运行失败",
}


def render_events(events: list[dict[str, Any]]) -> None:
    if not events:
        return
    with st.expander(f"运行事件（{len(events)}）"):
        for event in events[-60:]:
            label = EVENT_LABELS.get(event.get("type", ""), event.get("type", ""))
            timestamp = (event.get("created_at") or "")[11:19]
            st.markdown(f"`{timestamp}` **{label}** · `{event.get('type')}`")
