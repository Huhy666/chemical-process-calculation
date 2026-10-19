from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field

from .errors import ToolError
from .registry import Tool, register


class SensibleHeatInput(BaseModel):
    volumetric_flow_m3_h: float = Field(gt=0, description="体积流量，m³/h")
    density_kg_m3: float = Field(gt=0, description="密度，kg/m³")
    cp_kj_kgk: float = Field(gt=0, description="比热容，kJ/(kg·K)")
    t_in_c: float = Field(description="进口温度，°C")
    t_out_c: float = Field(description="出口温度，°C")


def sensible_heat_duty(inp: SensibleHeatInput) -> dict[str, Any]:
    mass_flow = inp.volumetric_flow_m3_h * inp.density_kg_m3
    delta_t = inp.t_out_c - inp.t_in_c
    duty_kw = mass_flow * inp.cp_kj_kgk * delta_t / 3600.0
    return {
        "mass_flow_kg_h": round(mass_flow, 3),
        "delta_t_k": round(delta_t, 4),
        "duty_kw": round(duty_kw, 4),
        "duty_kw_abs": round(abs(duty_kw), 4),
        "duty_mw": round(duty_kw / 1000.0, 6),
        "note": "正值表示物料升温吸热，负值表示物料降温放热。",
    }


class HeatExchangerInput(BaseModel):
    heat_duty_kw: float = Field(description="换热量，kW（吸热/放热均可，取绝对值计算）")
    overall_coeff_w_m2k: float = Field(gt=0, description="总传热系数 K，W/(m²·K)")
    hot_in_c: float = Field(description="热流体进口温度，°C")
    hot_out_c: float = Field(description="热流体出口温度，°C")
    cold_in_c: float = Field(description="冷流体进口温度，°C")
    cold_out_c: float = Field(description="冷流体出口温度，°C")


def _lmtd(hot_in: float, hot_out: float, cold_in: float, cold_out: float) -> float:
    d1 = hot_in - cold_out
    d2 = hot_out - cold_in
    if d1 <= 1e-9 or d2 <= 1e-9:
        raise ToolError(
            "逆流换热端温差必须为正："
            f"热进-冷出={d1:.3f} K，热出-冷进={d2:.3f} K。请检查温度安排。"
        )
    if abs(d1 - d2) < 1e-6:
        return d1
    return (d1 - d2) / math.log(d1 / d2)


def heat_exchanger_area(inp: HeatExchangerInput) -> dict[str, Any]:
    if inp.heat_duty_kw == 0:
        raise ToolError("换热量不能为 0")
    lmtd = _lmtd(inp.hot_in_c, inp.hot_out_c, inp.cold_in_c, inp.cold_out_c)
    q_w = abs(inp.heat_duty_kw) * 1000.0
    area = q_w / (inp.overall_coeff_w_m2k * lmtd)
    return {
        "heat_duty_kw": round(inp.heat_duty_kw, 4),
        "lmtd_k": round(lmtd, 4),
        "overall_coeff_w_m2k": inp.overall_coeff_w_m2k,
        "area_m2": round(area, 4),
        "heat_flux_w_m2": round(inp.overall_coeff_w_m2k * lmtd, 3),
        "arrangement": "按逆流计算，未考虑污垢热阻与校正系数",
    }


register(
    Tool(
        name="sensible_heat_duty",
        description=(
            "计算流体显热负荷：Q = 体积流量 × 密度 × 比热 × 温差。"
            "常用于加热/冷却所需换热量，结果单位 kW。"
        ),
        input_model=SensibleHeatInput,
        fn=sensible_heat_duty,
    )
)

register(
    Tool(
        name="heat_exchanger_area",
        description=(
            "按逆流对数平均温差（LMTD）估算换热面积：A = Q / (K × LMTD)。"
            "输入热流体与冷流体的进、出口温度，以及总传热系数 K。"
        ),
        input_model=HeatExchangerInput,
        fn=heat_exchanger_area,
    )
)
