from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field

from .errors import ToolError
from .registry import Tool, register

_G = 9.80665
_STANDARD_DN_MM = [
    15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150, 200, 250, 300,
    350, 400, 450, 500, 600, 700, 800, 900, 1000,
]


class PipeDiameterInput(BaseModel):
    volumetric_flow_m3_h: float = Field(gt=0, description="体积流量，m³/h")
    target_velocity_m_s: float = Field(gt=0, description="目标流速，m/s，例如液体常用 1~2 m/s")


def pipe_diameter(inp: PipeDiameterInput) -> dict[str, Any]:
    q_m3s = inp.volumetric_flow_m3_h / 3600.0
    d_m = math.sqrt(4.0 * q_m3s / (math.pi * inp.target_velocity_m_s))
    d_mm = d_m * 1000.0
    chosen = next((dn for dn in _STANDARD_DN_MM if dn >= d_mm), None)
    if chosen is None:
        raise ToolError(f"计算管径 {d_mm:.1f} mm 超出内置标准管径范围")
    actual_v = q_m3s / (math.pi * (chosen / 1000.0) ** 2 / 4.0)
    return {
        "calculated_diameter_mm": round(d_mm, 3),
        "recommended_dn_mm": chosen,
        "velocity_at_dn_m_s": round(actual_v, 4),
        "note": "推荐值为大于等于计算内径的最小标准 DN（按内径近似）；需结合壁厚校核。",
    }


class PipeVelocityInput(BaseModel):
    volumetric_flow_m3_h: float = Field(gt=0, description="体积流量，m³/h")
    diameter_mm: float = Field(gt=0, description="管道内径或公称直径，mm")


def pipe_velocity(inp: PipeVelocityInput) -> dict[str, Any]:
    q_m3s = inp.volumetric_flow_m3_h / 3600.0
    area = math.pi * (inp.diameter_mm / 1000.0) ** 2 / 4.0
    velocity = q_m3s / area
    return {
        "diameter_mm": inp.diameter_mm,
        "cross_section_m2": round(area, 8),
        "velocity_m_s": round(velocity, 4),
        "note": "按公称直径近似为内径计算，实际流速需用内径复核。",
    }


class PumpPowerInput(BaseModel):
    volumetric_flow_m3_h: float = Field(gt=0, description="体积流量，m³/h")
    head_m: float = Field(gt=0, description="泵扬程，m")
    density_kg_m3: float = Field(gt=0, description="介质密度，kg/m³")
    efficiency: float = Field(default=0.7, gt=0, le=1, description="泵效率，0~1，默认 0.7")


def pump_power(inp: PumpPowerInput) -> dict[str, Any]:
    q_m3s = inp.volumetric_flow_m3_h / 3600.0
    hydraulic_w = inp.density_kg_m3 * _G * q_m3s * inp.head_m
    hydraulic_kw = hydraulic_w / 1000.0
    shaft_kw = hydraulic_kw / inp.efficiency
    motor_kw = shaft_kw * 1.15
    return {
        "hydraulic_power_kw": round(hydraulic_kw, 4),
        "shaft_power_kw": round(shaft_kw, 4),
        "recommended_motor_kw": round(motor_kw, 3),
        "efficiency": inp.efficiency,
        "note": "轴功率 = 水力功率 / 效率；电机功率按轴功率 1.15 倍裕量估算。",
    }


register(
    Tool(
        name="pipe_diameter",
        description=(
            "根据体积流量和目标流速估算管道内径，并给出不小于计算值的推荐标准 DN 及对应流速。"
        ),
        input_model=PipeDiameterInput,
        fn=pipe_diameter,
    )
)

register(
    Tool(
        name="pipe_velocity",
        description="已知体积流量和管径，计算管道内平均流速。",
        input_model=PipeVelocityInput,
        fn=pipe_velocity,
    )
)

register(
    Tool(
        name="pump_power",
        description=(
            "估算泵功率：水力功率 = ρgQH，轴功率 = 水力功率/泵效率，并给出 1.15 倍裕量的电机功率。"
        ),
        input_model=PumpPowerInput,
        fn=pump_power,
    )
)
