from __future__ import annotations

import os
from typing import Any

import requests

BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000/api")


class ApiError(Exception):
    pass


def _request(method: str, path: str, **kwargs: Any) -> Any:
    try:
        response = requests.request(
            method, f"{BASE_URL}{path}", timeout=kwargs.pop("timeout", 120), **kwargs
        )
    except requests.RequestException as exc:
        raise ApiError(f"无法连接后端 {BASE_URL}：{exc}") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise ApiError(f"HTTP {response.status_code}：{detail}")
    if response.status_code == 204:
        return None
    return response.json()


def health() -> dict[str, Any]:
    return _request("GET", "/health", timeout=10)


def examples() -> list[dict[str, str]]:
    return _request("GET", "/examples", timeout=10)["examples"]


def tools() -> list[dict[str, Any]]:
    return _request("GET", "/tools", timeout=10)["tools"]


def create_run(question: str) -> dict[str, Any]:
    return _request("POST", "/runs", json={"question": question})


def approve(run_id: str, action: str, feedback: str | None = None) -> dict[str, Any]:
    return _request(
        "POST",
        f"/runs/{run_id}/approve",
        json={"action": action, "feedback": feedback},
    )


def get_run(run_id: str, after_event_id: int = 0) -> dict[str, Any]:
    return _request(
        "GET",
        f"/runs/{run_id}",
        params={"after_event_id": after_event_id},
    )


def list_runs(limit: int = 12) -> list[dict[str, Any]]:
    return _request("GET", "/runs", params={"limit": limit})["runs"]
