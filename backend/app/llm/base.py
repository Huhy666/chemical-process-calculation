from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


def extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise LLMError(f"模型输出中未找到 JSON 对象：{text[:300]}")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON 解析失败：{exc}；原文：{text[:300]}") from exc


class BaseLLM(ABC):
    name = "base"
    max_retries = 2

    @abstractmethod
    def _raw(self, system: str, user: str, json_mode: bool = False) -> str:
        """Send one request to the provider and return raw text."""

    def complete_text(self, system: str, user: str) -> str:
        return self._raw(system, user, json_mode=False)

    def complete_structured(
        self, system: str, user: str, schema: type[T]
    ) -> T:
        schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        prompt = (
            f"{user}\n\n"
            "请只返回一个 JSON 对象，不要输出 Markdown 代码块或额外解释。\n"
            f"JSON 必须符合以下 JSON Schema：\n{schema_text}"
        )
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            attempt_prompt = prompt
            if last_error is not None:
                attempt_prompt += (
                    f"\n\n上一次输出不合法：{last_error}\n"
                    "请严格按 Schema 重新输出完整 JSON。"
                )
            text = self._raw(system, attempt_prompt, json_mode=True)
            try:
                data = extract_json(text)
                return schema.model_validate(data)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise LLMError(
            f"结构化输出在 {self.max_retries + 1} 次尝试后仍失败：{last_error}"
        )
