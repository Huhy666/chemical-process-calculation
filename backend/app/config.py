from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM: mock | deepseek | claude
    llm_provider: str = "mock"
    llm_timeout_seconds: int = 90
    # Whether LLM calls should honor the operating system proxy settings.
    # Keep false when the local proxy is not running or only DeepSeek is used.
    llm_use_system_proxy: bool = False

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    anthropic_base_url: str = ""

    db_path: str = str(PROJECT_ROOT / "data" / "app.db")
    checkpoint_db_path: str = str(PROJECT_ROOT / "data" / "checkpoints.db")

    max_replans: int = 2
    max_plan_attempts: int = 3

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    backend_url_for_ui: str = "http://127.0.0.1:8000/api"

    @property
    def provider_label(self) -> str:
        return {
            "mock": "Mock（离线演示）",
            "deepseek": f"DeepSeek / {self.deepseek_model}",
            "claude": f"Claude / {self.anthropic_model}",
            "anthropic": f"Claude / {self.anthropic_model}",
        }.get(self.llm_provider.lower(), self.llm_provider)


settings = Settings()
