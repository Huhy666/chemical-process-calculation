from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import build_runtime
from app.api import runs
from app.config import settings
from app.db.engine import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.runtime = build_runtime(settings)
    yield
    app.state.runtime.close()


app = FastAPI(
    title="化工工艺计算 Plan & Execute Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {
        "name": "化工工艺计算 Plan & Execute Agent",
        "docs": "/docs",
        "health": "/api/health",
    }
