from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .errors import ToolError
from .registry import Tool, register

_DATA_FILE = Path(__file__).parent / "data" / "substances.json"
_DATA: dict[str, dict[str, Any]] = json.loads(_DATA_FILE.read_text(encoding="utf-8"))


def _normalize(value: str) -> str:
    return value.strip().lower().replace(" ", "").replace("-", "_").replace("　", "")


def find_substance(name: str) -> tuple[str | None, dict[str, Any] | None]:
    key = _normalize(name)
    if key in _DATA:
        return key, _DATA[key]
    for candidate_key, info in _DATA.items():
        aliases = info.get("aliases", [])
        if any(key == _normalize(alias) for alias in aliases):
            return candidate_key, info
        if key in {_normalize(info.get("name_zh", "")), _normalize(info.get("formula", ""))}:
            return candidate_key, info
    return None, None


class PropertiesInput(BaseModel):
    name: str = Field(description="物质名称、中文名或化学式，例如 water / 水 / C6H6")


def get_properties(inp: PropertiesInput) -> dict[str, Any]:
    key, info = find_substance(inp.name)
    if info is None:
        available = "、".join(f"{v['name_zh']}({v['formula']})" for v in _DATA.values())
        raise ToolError(
            f"物性库未收录 '{inp.name}'。当前收录：{available}。"
            "如需该物质数据，请先在 substances.json 中补充。"
        )
    return {
        "key": key,
        **{k: v for k, v in info.items() if k != "aliases"},
    }


class EmptyInput(BaseModel):
    pass


def list_substances(_: EmptyInput) -> dict[str, Any]:
    return {
        "count": len(_DATA),
        "substances": [
            {
                "key": key,
                "name_zh": info["name_zh"],
                "formula": info["formula"],
                "state": info["state"],
            }
            for key, info in _DATA.items()
        ],
    }


register(
    Tool(
        name="get_substance_properties",
        description=(
            "查询常用化工物质的物性数据：摩尔质量、密度、比热容、沸点、熔点、汽化潜热。"
            "当后续步骤需要密度或比热等参数时，先用本工具查询，再通过 ${步骤ID.字段名} 引用。"
        ),
        input_model=PropertiesInput,
        fn=get_properties,
    )
)

register(
    Tool(
        name="list_substances",
        description="列出物性库当前收录的全部物质名称与化学式。",
        input_model=EmptyInput,
        fn=list_substances,
    )
)
