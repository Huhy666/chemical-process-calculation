from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .errors import ToolError
from .registry import Tool, register

_R_KPA_M3_KMOL_K = 8.314462618


class IdealGasInput(BaseModel):
    pressure_kpa: float | None = Field(default=None, gt=0, description="压力，kPa")
    volume_m3: float | None = Field(default=None, gt=0, description="体积，m³")
    temperature_k: float | None = Field(default=None, gt=0, description="热力学温度，K")
    moles_kmol: float | None = Field(default=None, gt=0, description="摩尔量，kmol")


def ideal_gas(inp: IdealGasInput) -> dict[str, Any]:
    values = {
        "pressure_kpa": inp.pressure_kpa,
        "volume_m3": inp.volume_m3,
        "temperature_k": inp.temperature_k,
        "moles_kmol": inp.moles_kmol,
    }
    missing = [key for key, value in values.items() if value is None]
    if len(missing) != 1:
        raise ToolError(
            "理想气体计算需要且只能缺少一个参数；"
            f"当前缺少 {missing or '无'}。请提供压力、体积、温度、摩尔量中的三项。"
        )

    missing_key = missing[0]
    r = _R_KPA_M3_KMOL_K
    if missing_key == "pressure_kpa":
        values["pressure_kpa"] = values["moles_kmol"] * r * values["temperature_k"] / values["volume_m3"]
    elif missing_key == "volume_m3":
        values["volume_m3"] = values["moles_kmol"] * r * values["temperature_k"] / values["pressure_kpa"]
    elif missing_key == "temperature_k":
        values["temperature_k"] = values["pressure_kpa"] * values["volume_m3"] / (values["moles_kmol"] * r)
    elif missing_key == "moles_kmol":
        values["moles_kmol"] = values["pressure_kpa"] * values["volume_m3"] / (r * values["temperature_k"])

    return {
        **{key: round(value, 6) for key, value in values.items()},
        "solved_for": missing_key,
        "gas_constant": f"R = {r} kPa·m³/(kmol·K)",
        "note": "按理想气体状态方程 PV = nRT 计算，未考虑压缩因子。",
    }


register(
    Tool(
        name="ideal_gas",
        description=(
            "理想气体状态方程 PV=nRT 计算：给出压力、体积、温度、摩尔量中的任意三项，求解第四项。"
            "压力单位 kPa，体积 m³，温度 K，摩尔量 kmol。"
        ),
        input_model=IdealGasInput,
        fn=ideal_gas,
    )
)
