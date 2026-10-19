from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from app.agent.status import RunStatus
from app.config import settings
from app.db import repository as repo
from app.schemas.models import ApprovalRequest, CreateRunRequest
from app.tools import tool_catalog, tool_names

router = APIRouter()

EXAMPLES = [
    {
        "title": "水加热换热面积",
        "question": (
            "将 50 m³/h 的水从 20°C 加热到 80°C，热源为 120°C 饱和蒸汽，"
            "总传热系数 K=800 W/(m²·K)，求所需换热面积。"
        ),
    },
    {
        "title": "苯加氢物料衡算",
        "question": (
            "苯加氢制环己烷，进料苯 100 kmol/h、氢气 350 kmol/h，"
            "苯的转化率 95%，求反应器出口组成。"
        ),
    },
    {
        "title": "泵功率估算",
        "question": (
            "用泵把 30 m³/h 的水从低位槽送到 20 m 高的高位槽，泵效率 0.7，"
            "求泵的轴功率和推荐电机功率。"
        ),
    },
    {
        "title": "理想气体体积流量",
        "question": "250°C、1.2 MPa 下 10 kmol/h 氮气的体积流量是多少？",
    },
    {
        "title": "管径流速校核",
        "question": "DN100 管道输送 50 m³/h 水，求管内流速。",
    },
    {
        "title": "压力单位换算",
        "question": "把 1.2 MPa 换算成 bar。",
    },
]


def _runtime(request: Request):
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Agent 运行时尚未初始化")
    return runtime


@router.get("/health")
def health(request: Request) -> dict:
    runtime = _runtime(request)
    return {
        "status": "ok",
        "provider": settings.provider_label,
        "llm": runtime.llm.name,
        "tools": len(tool_names()),
    }


@router.get("/tools")
def tools() -> dict:
    return {"tools": tool_catalog()}


@router.get("/examples")
def examples() -> dict:
    return {"examples": EXAMPLES}


@router.post("/runs", status_code=202)
def create_run(
    payload: CreateRunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict:
    run_id = uuid.uuid4().hex
    repo.create_run(run_id, payload.question, RunStatus.CREATED)
    repo.add_event(run_id, "run.created", {"question": payload.question})
    background_tasks.add_task(_runtime(request).start, run_id, payload.question)
    return {"run_id": run_id, "status": RunStatus.CREATED}


@router.post("/runs/{run_id}/approve", status_code=202)
def approve_run(
    run_id: str,
    payload: ApprovalRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict:
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    if run["status"] != RunStatus.WAITING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=f"当前状态为 {run['status']}，只有 WAITING_APPROVAL 可以审批",
        )

    decision = {"action": payload.action, "feedback": payload.feedback}
    next_status = (
        RunStatus.EXECUTING if payload.action == "approve" else RunStatus.PLANNING
    )
    repo.update_run(run_id, status=next_status)
    background_tasks.add_task(_runtime(request).resume, run_id, decision)
    return {"run_id": run_id, "status": next_status}


@router.get("/runs")
def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    return {"runs": repo.list_runs(limit)}


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    after_event_id: int = Query(default=0, ge=0),
) -> dict:
    detail = repo.get_run_detail(run_id, after_event_id=after_event_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    return detail
