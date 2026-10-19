from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

_TMP = Path(tempfile.mkdtemp(prefix="chem-agent-tests-"))
os.environ["LLM_PROVIDER"] = "mock"
os.environ["DB_PATH"] = str(_TMP / "app.db")
os.environ["CHECKPOINT_DB_PATH"] = str(_TMP / "checkpoints.db")


@pytest.fixture(scope="session", autouse=True)
def initialize_database():
    from app.db.engine import init_db

    init_db()
    yield


@pytest.fixture()
def runtime():
    from app.agent.graph import build_runtime

    rt = build_runtime()
    yield rt
    rt.close()
