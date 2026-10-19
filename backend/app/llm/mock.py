from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel

from app.schemas.models import PlanOutput, PlanStep, ReplanOutput

from .base import BaseLLM, LLMError

T = TypeVar("T", bound=BaseModel)


def _num(pattern: str, text: str, default: float) -> float:
    match = re.search(pattern, text)
    if not match:
        return default
    return float(match.group(1))


def _flow_m3h(text: str, default: float = 50.0) -> float:
    return _num(r"(\d+(?:\.\d+)?)\s*(?:m3\s*/\s*h|m³\s*/\s*h|立方米\s*/\s*小时)", text, default)


def _percent(pattern: str, text: str, default: float) -> float:
    value = _num(pattern, text, default * 100.0 if default <= 1 else default)
    return value / 100.0 if value > 1 else value


class MockLLM(BaseLLM):
    """Deterministic offline LLM used for demos and tests.

    It understands the curated example questions; anything else raises a
    clear error so the demo never pretends to have planned something.
    """

    name = "mock"

    def _raw(self, system: str, user: str, json_mode: bool = False) -> str:
        if "汇报者" in system or "最终报告" in system:
            return self._final_report(user)
        raise LLMError("Mock 模式无法直接生成该文本输出")

    def complete_structured(self, system: str, user: str, schema: type[T]) -> T:
        if schema is PlanOutput:
            return self._plan(user)  # type: ignore[return-value]
        if schema is ReplanOutput:
            return ReplanOutput(
                give_up=True,
                reason="Mock 模式不支持自动重规划。请检查步骤参数，或切换到真实 LLM。",
                remaining_steps=[],
            )  # type: ignore[return-value]
        raise LLMError(f"Mock 模式不支持结构化输出：{schema.__name__}")

    # ---------------------------------------------------------------- planner

    def _question(self, user: str) -> str:
        marker = "用户问题："
        if marker not in user:
            raise LLMError("Mock 模式无法识别问题（缺少『用户问题：』标记）")
        text = user.split(marker, 1)[1]
        for stop in ("\n\n可用工具", "\n\n工具目录", "\n\n当前计划", "\n\n上一轮"):
            text = text.split(stop, 1)[0]
        return text.strip()

    def _plan(self, user: str) -> PlanOutput:
        question = self._question(user)
        if "水" in question and any(
            keyword in question for keyword in ("换热", "加热", "冷却", "换热面积")
        ):
            return self._water_heat_plan(question)
        if ("苯" in question and ("加氢" in question or "氢化" in question)) or (
            "环己烷" in question and "苯" in question
        ):
            return self._hydrogenation_plan(question)
        if "泵" in question:
            return self._pump_plan(question)
        if ("理想气体" in question) or (
            "氮气" in question and any(word in question for word in ("体积", "m³", "m3"))
        ):
            return self._ideal_gas_plan(question)
        if "管" in question and ("流速" in question or "管径" in question):
            return self._pipe_plan(question)
        if "换算" in question:
            return self._unit_plan(question)
        raise LLMError(
            "Mock 模式只内置了少量示例问题。请点击界面左侧的示例问题，"
            "或在 .env 中配置 DEEPSEEK_API_KEY / ANTHROPIC_API_KEY 后切换真实 LLM。"
        )

    def _water_heat_plan(self, question: str) -> PlanOutput:
        flow = _flow_m3h(question, 50.0)
        temperatures = [
            float(value)
            for value in re.findall(r"(\d+(?:\.\d+)?)\s*(?:°C|℃|摄氏度)", question)
        ]
        cold_in = temperatures[0] if len(temperatures) >= 2 else 20.0
        cold_out = temperatures[1] if len(temperatures) >= 2 else 80.0
        hot_temp = temperatures[2] if len(temperatures) >= 3 else 120.0
        overall_k = _num(r"K\s*[=＝]\s*(\d+(?:\.\d+)?)", question, 800.0)
        return PlanOutput(
            reasoning="先用物性数据计算水的显热负荷，再由 LMTD 估算换热面积。",
            steps=[
                PlanStep(
                    step_id="s1",
                    title="查询水的物性",
                    description="获取水的密度和比热容，供显热负荷计算使用。",
                    tool_name="get_substance_properties",
                    tool_args={"name": "水"},
                    expected_output="水的密度与比热容",
                ),
                PlanStep(
                    step_id="s2",
                    title="计算显热负荷",
                    description="按 Q = 体积流量 × 密度 × 比热 × 温差计算加热所需热量。",
                    tool_name="sensible_heat_duty",
                    tool_args={
                        "volumetric_flow_m3_h": flow,
                        "density_kg_m3": "${s1.density_kg_m3}",
                        "cp_kj_kgk": "${s1.cp_kj_kgk}",
                        "t_in_c": cold_in,
                        "t_out_c": cold_out,
                    },
                    expected_output="换热量 kW",
                ),
                PlanStep(
                    step_id="s3",
                    title="估算换热面积",
                    description="以热源温度、工艺进出口温度计算 LMTD，再按 A=Q/(K·LMTD) 估算面积。",
                    tool_name="heat_exchanger_area",
                    tool_args={
                        "heat_duty_kw": "${s2.duty_kw}",
                        "overall_coeff_w_m2k": overall_k,
                        "hot_in_c": hot_temp,
                        "hot_out_c": hot_temp,
                        "cold_in_c": cold_in,
                        "cold_out_c": cold_out,
                    },
                    expected_output="LMTD 与换热面积 m²",
                ),
            ],
        )

    def _hydrogenation_plan(self, question: str) -> PlanOutput:
        benzene = _num(r"苯[^0-9]{0,8}(\d+(?:\.\d+)?)\s*kmol", question, 100.0)
        hydrogen = _num(r"(?:氢气|氢)[^0-9]{0,8}(\d+(?:\.\d+)?)\s*kmol", question, 350.0)
        conversion = _percent(r"转化率[^0-9]{0,6}(\d+(?:\.\d+)?)\s*%?", question, 0.95)
        return PlanOutput(
            reasoning="以苯为限制反应物，按转化率计算反应进度与出口组成，再查询产物物性。",
            steps=[
                PlanStep(
                    step_id="s1",
                    title="物料衡算",
                    description="按苯加氢制环己烷计量式与转化率计算反应进度和出口组成。",
                    tool_name="stoichiometry_calc",
                    tool_args={
                        "reaction": {"C6H6": -1, "H2": -3, "C6H12": 1},
                        "feed_kmol_per_h": {"C6H6": benzene, "H2": hydrogen},
                        "limiting_reactant": "C6H6",
                        "conversion": conversion,
                    },
                    expected_output="反应进度与出口 kmol/h、kg/h",
                ),
                PlanStep(
                    step_id="s2",
                    title="查询产物物性",
                    description="查询环己烷的摩尔质量与沸点，便于后续工艺判断。",
                    tool_name="get_substance_properties",
                    tool_args={"name": "环己烷"},
                    expected_output="环己烷物性数据",
                ),
            ],
        )

    def _pump_plan(self, question: str) -> PlanOutput:
        flow = _flow_m3h(question, 30.0)
        head = _num(r"(\d+(?:\.\d+)?)\s*m\s*(?:高|的扬程|扬程)", question, -1.0)
        if head < 0:
            head = _num(r"扬程[^0-9]{0,6}(\d+(?:\.\d+)?)", question, 20.0)
        efficiency = _percent(r"效率[^0-9]{0,6}(\d+(?:\.\d+)?)\s*%?", question, 0.7)
        return PlanOutput(
            reasoning="先取水的密度，再按 ρgQH 估算水力功率与轴功率。",
            steps=[
                PlanStep(
                    step_id="s1",
                    title="查询水的密度",
                    description="获取水的密度用于泵功率计算。",
                    tool_name="get_substance_properties",
                    tool_args={"name": "水"},
                    expected_output="水的密度",
                ),
                PlanStep(
                    step_id="s2",
                    title="估算泵功率",
                    description="按流量、扬程、密度和效率计算水力功率、轴功率和电机功率。",
                    tool_name="pump_power",
                    tool_args={
                        "volumetric_flow_m3_h": flow,
                        "head_m": head,
                        "density_kg_m3": "${s1.density_kg_m3}",
                        "efficiency": efficiency,
                    },
                    expected_output="轴功率与推荐电机功率 kW",
                ),
            ],
        )

    def _ideal_gas_plan(self, question: str) -> PlanOutput:
        pressure_mpa = _num(r"(\d+(?:\.\d+)?)\s*MPa", question, -1.0)
        if pressure_mpa > 0:
            pressure_kpa = pressure_mpa * 1000.0
        else:
            pressure_kpa = _num(r"(\d+(?:\.\d+)?)\s*kPa", question, 101.325)
        temperature_c = _num(r"(\d+(?:\.\d+)?)\s*(?:°C|℃|摄氏度)", question, -1.0)
        temperature_k = temperature_c + 273.15 if temperature_c >= 0 else 298.15
        moles = _num(r"(\d+(?:\.\d+)?)\s*kmol", question, 1.0)
        return PlanOutput(
            reasoning="已知压力、温度和摩尔流量，使用 PV=nRT 求体积流量。",
            steps=[
                PlanStep(
                    step_id="s1",
                    title="求气体体积流量",
                    description="将温度换算为 K 后，用理想气体方程求体积。",
                    tool_name="ideal_gas",
                    tool_args={
                        "pressure_kpa": pressure_kpa,
                        "volume_m3": None,
                        "temperature_k": round(temperature_k, 2),
                        "moles_kmol": moles,
                    },
                    expected_output="体积流量 m³/h",
                )
            ],
        )

    def _pipe_plan(self, question: str) -> PlanOutput:
        flow = _flow_m3h(question, 50.0)
        diameter = _num(r"DN\s*(\d+)", question, -1.0)
        if diameter < 0:
            diameter = _num(r"(\d+(?:\.\d+)?)\s*mm", question, 100.0)
        if "管径" in question and "流速" in question:
            target = _num(r"流速[^0-9]{0,8}(\d+(?:\.\d+)?)", question, 1.5)
            return PlanOutput(
                reasoning="由目标流速反算所需内径，并选取标准 DN。",
                steps=[
                    PlanStep(
                        step_id="s1",
                        title="估算管径",
                        description="按 D=sqrt(4Q/(πv)) 计算内径并选取标准 DN。",
                        tool_name="pipe_diameter",
                        tool_args={
                            "volumetric_flow_m3_h": flow,
                            "target_velocity_m_s": target,
                        },
                        expected_output="计算管径与推荐 DN",
                    )
                ],
            )
        return PlanOutput(
            reasoning="已知流量和管径，直接计算平均流速。",
            steps=[
                PlanStep(
                    step_id="s1",
                    title="计算管内流速",
                    description="按 Q/A 计算管道平均流速。",
                    tool_name="pipe_velocity",
                    tool_args={
                        "volumetric_flow_m3_h": flow,
                        "diameter_mm": diameter,
                    },
                    expected_output="流速 m/s",
                )
            ],
        )

    def _unit_plan(self, question: str) -> PlanOutput:
        match = re.search(
            r"(\d+(?:\.\d+)?)\s*([A-Za-z0-9°³/·]+)\s*(?:换算成|换算为|转为|等于)\s*([A-Za-z0-9°³/·]+)",
            question,
        )
        if not match:
            raise LLMError(
                "Mock 模式无法解析该单位换算问题，请写成『把 1.2 MPa 换算成 bar』的形式。"
            )
        return PlanOutput(
            reasoning="直接调用单位换算工具。",
            steps=[
                PlanStep(
                    step_id="s1",
                    title="单位换算",
                    description="按给定数值与单位完成换算。",
                    tool_name="unit_convert",
                    tool_args={
                        "value": float(match.group(1)),
                        "from_unit": match.group(2),
                        "to_unit": match.group(3),
                    },
                    expected_output="换算结果",
                )
            ],
        )

    # --------------------------------------------------------------- finalizer

    def _final_report(self, user: str) -> str:
        marker = "步骤结果 JSON："
        if marker not in user:
            return "## 计算结果\n\n（Mock 模式未找到结构化结果）"
        raw = user.split(marker, 1)[1].strip()
        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            return f"## 计算结果\n\n```json\n{raw}\n```"

        plan = {step["step_id"]: step for step in data.get("plan", [])}
        observations: dict[str, Any] = data.get("observations", {})
        lines = ["## 计算结果摘要", "", "> 当前为 Mock 离线模式，以下数值由本地确定性工具计算。", ""]
        if not observations:
            lines.append("没有可用的步骤结果。")
        for index, (step_id, result) in enumerate(observations.items(), start=1):
            step = plan.get(step_id, {})
            title = step.get("title", step_id)
            tool = step.get("tool_name", "")
            lines.append(f"### {index}. {title}（`{tool}`）")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(result, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")
        error = data.get("error")
        if error:
            lines.append(f"**执行提示**：{error}")
        lines.append("")
        lines.append("如需处理非示例问题，请在 `.env` 中配置真实 LLM 的 API Key。")
        return "\n".join(lines)
