from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .errors import ToolError

_TOOLS: dict[str, "Tool"] = {}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    fn: Callable[[Any], dict[str, Any]]

    def run(self, raw_args: dict[str, Any]) -> dict[str, Any]:
        try:
            parsed = self.input_model.model_validate(raw_args)
        except ValidationError as exc:
            raise ToolError(f"参数校验失败：{exc.errors(include_url=False)}") from exc
        try:
            return self.fn(parsed)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface any tool failure as ToolError
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc

    def catalog_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }


def register(tool: Tool) -> None:
    if tool.name in _TOOLS:
        raise ValueError(f"工具重复注册：{tool.name}")
    _TOOLS[tool.name] = tool


def get_tool(name: str) -> Tool:
    tool = _TOOLS.get(name)
    if tool is None:
        available = ", ".join(sorted(_TOOLS))
        raise ToolError(f"未知工具 '{name}'。可用工具：{available}")
    return tool


def tool_names() -> list[str]:
    return sorted(_TOOLS)


def tool_catalog() -> list[dict[str, Any]]:
    return [_TOOLS[name].catalog_entry() for name in sorted(_TOOLS)]
