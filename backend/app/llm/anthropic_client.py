from __future__ import annotations

from anthropic import Anthropic

try:  # newer Anthropic SDKs use httpx2
    import httpx2 as httpx_client
except ImportError:  # older SDKs use httpx
    import httpx as httpx_client

from .base import BaseLLM, LLMError


class AnthropicLLM(BaseLLM):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "",
        timeout: int = 90,
        use_system_proxy: bool = False,
    ) -> None:
        if not api_key:
            raise LLMError("Claude 缺少 ANTHROPIC_API_KEY，请在 .env 中配置")
        http_client = httpx_client.Client(
            trust_env=use_system_proxy,
            timeout=float(timeout),
        )
        kwargs = {"api_key": api_key, "http_client": http_client}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = Anthropic(**kwargs)
        self.model = model
        self.name = "claude"

    def _raw(self, system: str, user: str, json_mode: bool = False) -> str:
        system_prompt = system
        if json_mode:
            system_prompt += "\n你只输出 JSON 对象，不输出任何其他文字。"
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.2,
                system=system_prompt,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(
                f"claude 请求失败：{type(exc).__name__}: {exc}。"
                "如使用代理访问 Anthropic，请将 LLM_USE_SYSTEM_PROXY 设为 true。"
            ) from exc
        parts = [block.text for block in response.content if block.type == "text"]
        return "".join(parts)
