from __future__ import annotations

from app.config import Settings

from .anthropic_client import AnthropicLLM
from .base import BaseLLM, LLMError
from .mock import MockLLM
from .openai_compat import OpenAICompatibleLLM


def build_llm(settings: Settings) -> BaseLLM:
    provider = settings.llm_provider.strip().lower()
    if provider == "mock":
        return MockLLM()
    if provider == "deepseek":
        return OpenAICompatibleLLM(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout=settings.llm_timeout_seconds,
            use_system_proxy=settings.llm_use_system_proxy,
            name="deepseek",
        )
    if provider in {"claude", "anthropic"}:
        return AnthropicLLM(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            base_url=settings.anthropic_base_url,
            timeout=settings.llm_timeout_seconds,
            use_system_proxy=settings.llm_use_system_proxy,
        )
    raise LLMError(
        f"未知 LLM_PROVIDER '{settings.llm_provider}'，可选值：mock、deepseek、claude"
    )
