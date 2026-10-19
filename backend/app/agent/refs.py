from __future__ import annotations

import re
from typing import Any

from app.tools.errors import RefResolutionError

_REF_PATTERN = re.compile(r"^\$\{([^}]+)\}$")


def _lookup(path: str, observations: dict[str, Any]) -> Any:
    parts = path.split(".")
    if not parts or parts[0] not in observations:
        raise RefResolutionError(
            f"引用 '{path}' 无法解析：步骤 '{parts[0] if parts else path}' 尚无结果"
        )
    current: Any = observations[parts[0]]
    for part in parts[1:]:
        if isinstance(current, dict):
            if part not in current:
                raise RefResolutionError(f"引用 '{path}' 无法解析：字段 '{part}' 不存在")
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise RefResolutionError(
                    f"引用 '{path}' 无法解析：'{part}' 不是列表索引"
                ) from exc
            if index < 0 or index >= len(current):
                raise RefResolutionError(f"引用 '{path}' 无法解析：索引越界")
            current = current[index]
        else:
            raise RefResolutionError(f"引用 '{path}' 无法解析：'{part}' 之前的值为标量")
    return current


def resolve_refs(value: Any, observations: dict[str, Any]) -> Any:
    """Recursively replace ${step_id.field} references with prior step results."""
    if isinstance(value, str):
        match = _REF_PATTERN.match(value.strip())
        if match:
            return _lookup(match.group(1), observations)
        return value
    if isinstance(value, dict):
        return {key: resolve_refs(item, observations) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_refs(item, observations) for item in value]
    return value
