from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .errors import ToolError
from .registry import Tool, register

# unit -> (category, factor to base unit)
_LINEAR_UNITS: dict[str, tuple[str, float]] = {
    # pressure, base kPa
    "pa": ("pressure", 0.001),
    "kpa": ("pressure", 1.0),
    "mpa": ("pressure", 1000.0),
    "bar": ("pressure", 100.0),
    "atm": ("pressure", 101.325),
    "mmhg": ("pressure", 0.133322),
    # volumetric flow, base m3/h
    "m3/h": ("flow", 1.0),
    "m3/s": ("flow", 3600.0),
    "m3/min": ("flow", 60.0),
    "l/min": ("flow", 0.06),
    "l/h": ("flow", 0.001),
    # mass, base kg
    "kg": ("mass", 1.0),
    "t": ("mass", 1000.0),
    "g": ("mass", 0.001),
    "lb": ("mass", 0.45359237),
    # power, base kW
    "w": ("power", 0.001),
    "kw": ("power", 1.0),
    "mw": ("power", 1000.0),
    "hp": ("power", 0.745699872),
    "kcal/h": ("power", 0.001163),
    # energy, base kJ
    "kj": ("energy", 1.0),
    "kcal": ("energy", 4.184),
    "kwh": ("energy", 3600.0),
    "btu": ("energy", 1.05505585262),
    # length, base m
    "m": ("length", 1.0),
    "mm": ("length", 0.001),
    "cm": ("length", 0.01),
    "in": ("length", 0.0254),
    "ft": ("length", 0.3048),
    # volume, base m3
    "m3": ("volume", 1.0),
    "l": ("volume", 0.001),
}

_TEMPERATURE_UNITS = {"c", "k", "f"}


def _normalize_unit(unit: str) -> str:
    return (
        unit.strip().lower()
        .replace(" ", "")
        .replace("°", "")
        .replace("³", "3")
        .replace("·", "")
        .replace("∕", "/")
    )


def _temperature_to_c(value: float, unit: str) -> float:
    if unit == "c":
        return value
    if unit == "k":
        return value - 273.15
    return (value - 32.0) * 5.0 / 9.0


def _temperature_from_c(value_c: float, unit: str) -> float:
    if unit == "c":
        return value_c
    if unit == "k":
        return value_c + 273.15
    return value_c * 9.0 / 5.0 + 32.0


class UnitConvertInput(BaseModel):
    value: float = Field(description="待换算数值")
    from_unit: str = Field(description="原单位，例如 m3/h、kPa、°C、kW")
    to_unit: str = Field(description="目标单位，例如 L/min、MPa、K、kcal/h")


def unit_convert(inp: UnitConvertInput) -> dict[str, Any]:
    src = _normalize_unit(inp.from_unit)
    dst = _normalize_unit(inp.to_unit)

    if src in _TEMPERATURE_UNITS or dst in _TEMPERATURE_UNITS:
        if src not in _TEMPERATURE_UNITS or dst not in _TEMPERATURE_UNITS:
            raise ToolError("温度单位只能与温度单位互相换算（C/K/F）")
        celsius = _temperature_to_c(inp.value, src)
        result = _temperature_from_c(celsius, dst)
        return {
            "value": inp.value,
            "from_unit": inp.from_unit,
            "to_unit": inp.to_unit,
            "result": round(result, 6),
            "category": "temperature",
        }

    if src not in _LINEAR_UNITS:
        raise ToolError(f"不支持的单位 '{inp.from_unit}'。支持：{', '.join(sorted(_LINEAR_UNITS))}")
    if dst not in _LINEAR_UNITS:
        raise ToolError(f"不支持的单位 '{inp.to_unit}'。支持：{', '.join(sorted(_LINEAR_UNITS))}")

    src_category, src_factor = _LINEAR_UNITS[src]
    dst_category, dst_factor = _LINEAR_UNITS[dst]
    if src_category != dst_category:
        raise ToolError(
            f"单位类别不一致：{inp.from_unit} 属于 {src_category}，{inp.to_unit} 属于 {dst_category}"
        )

    result = inp.value * src_factor / dst_factor
    return {
        "value": inp.value,
        "from_unit": inp.from_unit,
        "to_unit": inp.to_unit,
        "result": round(result, 8),
        "category": src_category,
    }


register(
    Tool(
        name="unit_convert",
        description=(
            "常用工程单位换算，支持压力（Pa/kPa/MPa/bar/atm/mmHg）、体积流量、质量、功率、能量、"
            "长度、体积与温度（C/K/F）。"
        ),
        input_model=UnitConvertInput,
        fn=unit_convert,
    )
)
