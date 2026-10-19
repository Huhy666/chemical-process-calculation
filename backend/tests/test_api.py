from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

QUESTION = "DN100 管道输送 50 m³/h 水，求管内流速。"


def test_health_and_catalog():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        tools = client.get("/api/tools").json()["tools"]
        names = {tool["name"] for tool in tools}
        assert {"pipe_velocity", "heat_exchanger_area", "ideal_gas"} <= names

        examples = client.get("/api/examples").json()["examples"]
        assert len(examples) >= 3


def test_full_run_flow():
    with TestClient(app) as client:
        created = client.post("/api/runs", json={"question": QUESTION})
        assert created.status_code == 202
        run_id = created.json()["run_id"]

        detail = client.get(f"/api/runs/{run_id}").json()
        assert detail["run"]["status"] == "WAITING_APPROVAL"
        assert len(detail["steps"]) == 1

        double_approve = client.post(
            f"/api/runs/{run_id}/approve", json={"action": "approve"}
        )
        assert double_approve.status_code == 202

        detail = client.get(f"/api/runs/{run_id}").json()
        assert detail["run"]["status"] == "COMPLETED"

        conflict = client.post(
            f"/api/runs/{run_id}/approve", json={"action": "approve"}
        )
        assert conflict.status_code == 409

        incremental = client.get(
            f"/api/runs/{run_id}", params={"after_event_id": 999999}
        ).json()
        assert incremental["events"] == []


def test_missing_run_returns_404():
    with TestClient(app) as client:
        assert client.get("/api/runs/does-not-exist").status_code == 404
        assert (
            client.post(
                "/api/runs/does-not-exist/approve", json={"action": "approve"}
            ).status_code
            == 404
        )
