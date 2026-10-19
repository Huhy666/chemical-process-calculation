from __future__ import annotations

import time
from typing import Any

import streamlit as st

import api_client as api
from components.plan_card import render_plan
from components.timeline import render_events, render_steps
from components.timeline import STEP_ICONS

st.set_page_config(
    page_title="化工工艺计算 Agent",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.8rem; max-width: 1100px;}
    h1, h2, h3 {letter-spacing: -0.02em;}
    [data-testid="stSidebar"] {background: #f7f7f9;}
    </style>
    """,
    unsafe_allow_html=True,
)

STATUS_LABELS = {
    "CREATED": "已创建",
    "PLANNING": "规划中",
    "WAITING_APPROVAL": "待人工审批",
    "EXECUTING": "执行中",
    "REPLANNING": "重规划中",
    "COMPLETED": "已完成",
    "FAILED": "失败",
}

STATUS_ICONS = {
    "CREATED": "🕐",
    "PLANNING": "🧠",
    "WAITING_APPROVAL": "🖐️",
    "EXECUTING": "⚙️",
    "REPLANNING": "🔁",
    "COMPLETED": "✅",
    "FAILED": "❌",
}

IN_PROGRESS = {"CREATED", "PLANNING", "EXECUTING", "REPLANNING"}
TERMINAL = {"COMPLETED", "FAILED"}

st.session_state.setdefault("run_id", None)
st.session_state.setdefault("last_event_id", 0)
st.session_state.setdefault("question", None)


def status_label(status: str) -> str:
    return f"{STATUS_ICONS.get(status, '•')} {STATUS_LABELS.get(status, status)}"


def drive_run(
    run_id: str,
    action: str | None = None,
    feedback: str | None = None,
    max_wait: int = 240,
) -> None:
    """Poll the backend until the run needs approval or reaches a terminal state."""
    if action is not None:
        try:
            api.approve(run_id, action, feedback)
        except api.ApiError as exc:
            st.error(str(exc))
            return

    placeholder = st.empty()
    last_id = int(st.session_state.get("last_event_id", 0))
    deadline = time.time() + max_wait

    while time.time() < deadline:
        try:
            detail = api.get_run(run_id, after_event_id=last_id)
        except api.ApiError as exc:
            placeholder.error(str(exc))
            return
        for event in detail["events"]:
            last_id = max(last_id, int(event["id"]))
        st.session_state["last_event_id"] = last_id
        with placeholder.container():
            _render_live(detail)
        if detail["run"]["status"] in {"WAITING_APPROVAL", "COMPLETED", "FAILED"}:
            break
        time.sleep(0.8)
    else:
        st.warning("等待超时，页面将刷新。可从左侧历史记录重新打开这次运行。")

    time.sleep(0.2)
    st.rerun()


def _render_live(detail: dict[str, Any]) -> None:
    run = detail["run"]
    st.markdown(f"**{status_label(run['status'])}**")
    steps = detail.get("steps", [])
    if not steps:
        st.caption("Agent 正在分析问题并生成计划…")
        return
    for index, step in enumerate(steps, start=1):
        icon = STEP_ICONS.get(step.get("status", "pending"), "⚪")
        st.markdown(
            f"{icon} **{index}. {step.get('title', '')}** "
            f"<span style='color:#6b7280;font-size:0.82rem'>"
            f"`{step.get('status', '')}`</span>",
            unsafe_allow_html=True,
        )


def render_header(run: dict[str, Any]) -> None:
    left, right = st.columns([5, 1])
    with left:
        st.markdown(f"### {run['question']}")
    with right:
        st.markdown(
            f"<div style='text-align:right;font-size:0.95rem;padding-top:0.35rem'>"
            f"{status_label(run['status'])}</div>",
            unsafe_allow_html=True,
        )
    st.caption(
        f"运行 ID：{run['id'][:12]} · 重规划次数：{run['replan_count']} · "
        f"创建时间：{run['created_at'][:19]} UTC"
    )


def render_detail(detail: dict[str, Any]) -> None:
    run = detail["run"]
    steps = detail.get("steps", [])
    events = detail.get("events", [])

    render_header(run)

    if run.get("error"):
        st.error(run["error"])

    if run.get("plan"):
        render_plan(run["plan"])

    if run["status"] == "WAITING_APPROVAL":
        with st.container(border=True):
            st.markdown("#### 等待审批")
            st.write(
                "请检查计划中的工具与参数。批准后 Agent 将按步骤执行确定性计算；"
                "如计划不合理，可填写意见驳回，Agent 会重新规划。"
            )
            feedback = st.text_input(
                "驳回意见（驳回时使用）",
                key=f"feedback-{run['id']}",
                placeholder="例如：请把热源温度改为 130°C 并补充安全裕量",
            )
            col_approve, col_reject = st.columns(2)
            if col_approve.button(
                "✅ 批准并执行", type="primary", use_container_width=True
            ):
                drive_run(run["id"], action="approve")
            if col_reject.button("↩️ 驳回并重新规划", use_container_width=True):
                drive_run(
                    run["id"],
                    action="reject",
                    feedback=feedback.strip() or "请调整计划",
                )

    if steps:
        render_steps(steps)

    if run["status"] in TERMINAL and run.get("final_answer"):
        st.markdown("#### 最终报告")
        if run["status"] == "FAILED":
            st.warning("本次运行未完整完成，以下为已有结果或错误说明。")
        with st.container(border=True):
            st.markdown(run["final_answer"])

    if events:
        render_events(events)


# --------------------------------------------------------------------- sidebar

with st.sidebar:
    st.markdown("## ⚗️ 化工工艺计算 Agent")
    st.caption("Plan → 人工审批 → 确定性执行 → 报告")

    try:
        health = api.health()
        st.success(f"后端在线 · {health['provider']}")
        st.caption(f"已注册工具：{health['tools']} 个")
    except api.ApiError as exc:
        st.error("后端未连接")
        st.code(
            "cd D:/heima/AI/newwork\n"
            "PYTHONPATH=backend .venv/Scripts/python.exe -m uvicorn app.main:app "
            "--host 127.0.0.1 --port 8000",
            language="bash",
        )
        st.caption(str(exc))
        st.stop()

    st.divider()
    st.markdown("**示例问题**")
    try:
        examples = api.examples()
    except api.ApiError:
        examples = []
    for example in examples:
        if st.button(
            example["title"],
            key=f"example-{example['title']}",
            use_container_width=True,
            help=example["question"],
        ):
            st.session_state["pending_question"] = example["question"]
            st.session_state["run_id"] = None
            st.session_state["last_event_id"] = 0
            st.rerun()

    st.divider()
    st.markdown("**历史运行**")
    try:
        recent_runs = api.list_runs(10)
    except api.ApiError:
        recent_runs = []
    if not recent_runs:
        st.caption("暂无运行记录")
    for item in recent_runs:
        question = item["question"]
        short = question if len(question) <= 26 else question[:26] + "…"
        if st.button(
            f"{STATUS_ICONS.get(item['status'], '•')} {short}",
            key=f"history-{item['id']}",
            use_container_width=True,
            help=question,
        ):
            st.session_state["run_id"] = item["id"]
            st.session_state["question"] = question
            st.session_state["last_event_id"] = 0
            st.rerun()

    if st.button("＋ 新建对话", use_container_width=True):
        st.session_state["run_id"] = None
        st.session_state["question"] = None
        st.session_state["last_event_id"] = 0
        st.rerun()

    st.divider()
    st.caption(
        "计算全部由本地确定性工具完成；LLM 只负责计划、重规划与报告撰写。"
        "Mock 模式可离线演示内置示例，真实问题请配置 DeepSeek 或 Claude API Key。"
    )


# ------------------------------------------------------------------------ main

pending = st.session_state.pop("pending_question", None)
if pending:
    try:
        created = api.create_run(pending)
    except api.ApiError as exc:
        st.error(f"创建运行失败：{exc}")
        st.stop()
    st.session_state["run_id"] = created["run_id"]
    st.session_state["question"] = pending
    st.session_state["last_event_id"] = 0
    st.rerun()

run_id = st.session_state.get("run_id")

if run_id is None:
    st.markdown("# 化工工艺计算 Agent")
    st.markdown(
        "把化工计算问题拆成可检查的计划，**经你批准后**逐步调用确定性工具执行，"
        "最后生成带步骤引用的计算报告。"
    )
    st.markdown("#### 能做什么")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            "**物性与衡算**\n\n- 常用物质物性查询\n- 摩尔质量与元素组成\n"
            "- 反应进度与出口组成"
        )
    with col2:
        st.markdown(
            "**传热与流体**\n\n- 显热负荷计算\n- LMTD 与换热面积估算\n"
            "- 管径、流速、泵功率"
        )
    with col3:
        st.markdown(
            "**气体与单位**\n\n- 理想气体 PV=nRT\n- 压力/流量/功率/温度换算\n"
            "- 步骤间自动引用结果"
        )
    st.info("从左侧选择一个示例问题，或在下方输入你的问题。")
else:
    try:
        detail = api.get_run(run_id)
    except api.ApiError as exc:
        st.error(f"读取运行失败：{exc}")
        st.stop()

    render_detail(detail)
    if detail["run"]["status"] in IN_PROGRESS:
        drive_run(run_id)

question = st.chat_input("描述你的化工计算问题…")
if question:
    st.session_state["pending_question"] = question
    st.rerun()
