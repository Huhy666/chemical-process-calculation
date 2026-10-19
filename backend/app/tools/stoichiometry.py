from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from .errors import ToolError
from .registry import Tool, register

_ATOMIC_WEIGHTS: dict[str, float] = {
    "H": 1.008, "He": 4.0026, "Li": 6.94, "B": 10.81, "C": 12.011, "N": 14.007,
    "O": 15.999, "F": 18.998, "Na": 22.990, "Mg": 24.305, "Al": 26.982,
    "Si": 28.085, "P": 30.974, "S": 32.06, "Cl": 35.45, "Ar": 39.948,
    "K": 39.098, "Ca": 40.078, "Ti": 47.867, "Cr": 52.00, "Mn": 54.938,
    "Fe": 55.845, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38, "Br": 79.904,
    "Ag": 107.868, "I": 126.90, "Ba": 137.327, "Sn": 118.710, "Pb": 207.2,
}

_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*\.?\d*)")


def parse_formula(formula: str) -> dict[str, float]:
    """Parse a simple chemical formula such as C6H6 or H2SO4.

    Parentheses and hydrates are intentionally not supported in this demo.
    """
    raw = formula.strip().replace(" ", "")
    if not raw:
        raise ToolError("化学式不能为空")
    pos = 0
    counts: dict[str, float] = {}
    for match in _TOKEN.finditer(raw):
        if match.start() != pos:
            raise ToolError(f"无法解析化学式 '{formula}'，请使用类似 C6H6、H2SO4 的形式")
        element, number_text = match.group(1), match.group(2)
        if element not in _ATOMIC_WEIGHTS:
            raise ToolError(f"未知元素 '{element}'（化学式：{formula}）")
        number = float(number_text) if number_text else 1.0
        if number <= 0:
            raise ToolError(f"化学式 '{formula}' 中元素 '{element}' 的个数必须为正数")
        counts[element] = counts.get(element, 0.0) + number
        pos = match.end()
    if pos != len(raw):
        raise ToolError(f"无法解析化学式 '{formula}'，请使用类似 C6H6、H2SO4 的形式")
    return counts


def formula_molar_mass(formula: str) -> float:
    counts = parse_formula(formula)
    return sum(_ATOMIC_WEIGHTS[el] * n for el, n in counts.items())


class MolarMassInput(BaseModel):
    formula: str = Field(description="化学式，例如 C6H6、H2SO4、CaCO3")


def molar_mass(inp: MolarMassInput) -> dict[str, Any]:
    counts = parse_formula(inp.formula)
    g_per_mol = sum(_ATOMIC_WEIGHTS[el] * n for el, n in counts.items())
    return {
        "formula": inp.formula.strip(),
        "molar_mass_g_mol": round(g_per_mol, 4),
        "molar_mass_kg_kmol": round(g_per_mol, 4),
        "composition": {
            el: {"atoms": n, "mass_fraction": round(_ATOMIC_WEIGHTS[el] * n / g_per_mol, 5)}
            for el, n in counts.items()
        },
    }


class StoichiometryInput(BaseModel):
    reaction: dict[str, float] = Field(
        description=(
            "反应计量系数，反应物为负、产物为正。例如苯加氢："
            '{"C6H6": -1, "H2": -3, "C6H12": 1}'
        )
    )
    feed_kmol_per_h: dict[str, float] = Field(
        description="进料摩尔流量，单位 kmol/h，例如 {\"C6H6\": 100, \"H2\": 350}"
    )
    limiting_reactant: str = Field(description="指定的限制反应物（化学式），例如 C6H6")
    conversion: float = Field(gt=0, le=1, description="限制反应物转化率，0~1 之间")


def stoichiometry_calc(inp: StoichiometryInput) -> dict[str, Any]:
    reaction = {k: float(v) for k, v in inp.reaction.items()}
    feed = {k: float(v) for k, v in inp.feed_kmol_per_h.items()}

    if inp.limiting_reactant not in reaction:
        raise ToolError(f"限制反应物 '{inp.limiting_reactant}' 不在反应计量系数中")
    if inp.limiting_reactant not in feed:
        raise ToolError(f"限制反应物 '{inp.limiting_reactant}' 不在进料组成中")

    limiting_coeff = reaction[inp.limiting_reactant]
    if limiting_coeff >= 0:
        raise ToolError("限制反应物在 reaction 中的系数必须为负数")

    for species, flow in feed.items():
        if flow < 0:
            raise ToolError(f"进料流量不能为负：{species}={flow}")

    extent = feed[inp.limiting_reactant] * inp.conversion / (-limiting_coeff)
    if extent <= 0:
        raise ToolError("反应进度必须为正，请检查进料与转化率")

    shortages: list[str] = []
    for species, coeff in reaction.items():
        if coeff >= 0:
            continue
        needed = -coeff * extent
        available = feed.get(species, 0.0)
        if available + 1e-9 < needed:
            shortages.append(
                f"{species} 需要 {needed:.4f} kmol/h，但仅进料 {available:.4f} kmol/h"
            )
    if shortages:
        raise ToolError(
            "限制反应物设定与进料不符，以下反应物不足：" + "；".join(shortages)
        )

    species_all = sorted(set(reaction) | set(feed))
    outlet: dict[str, float] = {}
    for species in species_all:
        value = feed.get(species, 0.0) + reaction.get(species, 0.0) * extent
        if value < -1e-7:
            raise ToolError(f"{species} 出口流量为负，请检查计量系数与进料")
        outlet[species] = round(max(value, 0.0), 6)

    outlet_mass: dict[str, float] = {}
    molar_masses: dict[str, float] = {}
    for species, flow in outlet.items():
        try:
            mm = formula_molar_mass(species)
        except ToolError:
            continue
        molar_masses[species] = round(mm, 4)
        outlet_mass[species] = round(flow * mm, 3)

    return {
        "extent_kmol_per_h": round(extent, 6),
        "conversion_basis": {
            inp.limiting_reactant: inp.conversion,
        },
        "feed_kmol_per_h": {k: round(v, 6) for k, v in feed.items()},
        "outlet_kmol_per_h": outlet,
        "outlet_kg_per_h": outlet_mass,
        "molar_mass_g_mol": molar_masses,
        "products_formed": [
            s for s, c in reaction.items() if c > 0 and feed.get(s, 0.0) == 0.0
        ],
    }


register(
    Tool(
        name="molar_mass",
        description="根据化学式计算摩尔质量（g/mol 与 kg/kmol），并给出元素质量分数。",
        input_model=MolarMassInput,
        fn=molar_mass,
    )
)

register(
    Tool(
        name="stoichiometry_calc",
        description=(
            "按反应计量系数、进料组成和限制反应物转化率计算反应进度与出口组成。"
            "reaction 中反应物系数为负、产物为正；输出包含出口 kmol/h 与 kg/h。"
        ),
        input_model=StoichiometryInput,
        fn=stoichiometry_calc,
    )
)
