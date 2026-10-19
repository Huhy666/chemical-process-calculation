from __future__ import annotations

from typing import Any

import streamlit as st


def render_plan(plan: list[dict[str, Any]]) -> None:
    if not plan:
        return
    st.markdown("#### 执行计划")
    st.caption("计划由 LLM 生成；每一步都绑定确定性工具，数值计算不依赖模型自由发挥。")
    for index, step in enumerate(plan, start=1):
        with st.container(border=True):
            head_left, head_right = st.columns([4, 1])
            with head_left:
                st.markdown(f"**步骤 {index} · {step.get('title', '')}**")
                st.caption(
                    f"{step.get('step_id', '')} · `{step.get('tool_name', '')}`"
                )
            with head_right:
                st.markdown(
                    f"<div style='text-align:right;color:#6b7280;font-size:0.8rem'>"
                    f"{step.get('step_id', '')}</div>",
                    unsafe_allow_html=True,
                )
            st.write(step.get("description", ""))
            expected = step.get("expected_output")
            if expected:
                st.caption(f"预期产出：{expected}")
            with st.expander("工具参数"):
                st.json(step.get("tool_args", {}))
