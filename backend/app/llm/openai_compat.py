from __future__ import annotations

import requests

from .base import BaseLLM, LLMError


class OpenAICompatibleLLM(BaseLLM):
    """Client for OpenAI-compatible providers such as DeepSeek.

    Uses requests directly so we can control whether system proxy settings are
    honored. A local proxy that is not running is a common cause of opaque SSL
    EOF errors, so ``LLM_USE_SYSTEM_PROXY`` defaults to false.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 90,
        use_system_proxy: bool = False,
        name: str = "openai-compatible",
    ) -> None:
        if not api_key:
            raise LLMError(f"{name} 缺少 API Key，请在 .env 中配置")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.name = name
        self.session = requests.Session()
        self.session.trust_env = use_system_proxy
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

    def _raw(self, system: str, user: str, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise LLMError(
                f"{self.name} 请求失败：{type(exc).__name__}: {exc}。"
                "若本机配置了代理，请检查代理是否可用；"
                "直连可用的场景可将 LLM_USE_SYSTEM_PROXY 设为 false。"
            ) from exc

        if response.status_code >= 400:
            raise LLMError(
                f"{self.name} API 返回 {response.status_code}：{response.text[:500]}"
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"{self.name} 响应解析失败：{response.text[:300]}"
            ) from exc
        return content or ""
