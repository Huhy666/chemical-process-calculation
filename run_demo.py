"""Launch the backend and Streamlit frontend together for a local demo."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _terminate(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    env = os.environ.copy()
    backend_path = str(ROOT / "backend")
    env["PYTHONPATH"] = (
        backend_path + os.pathsep + env["PYTHONPATH"]
        if env.get("PYTHONPATH")
        else backend_path
    )

    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=ROOT,
        env=env,
    )
    frontend: subprocess.Popen | None = None

    try:
        time.sleep(2.5)
        if backend.poll() is not None:
            print("后端启动失败，请检查上方错误信息。")
            return 1

        frontend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "frontend/app.py",
                "--server.headless",
                "true",
                "--server.port",
                "8501",
                "--browser.gatherUsageStats",
                "false",
            ],
            cwd=ROOT,
            env=env,
        )
        time.sleep(3.0)
        webbrowser.open("http://127.0.0.1:8501")
        print("后端:  http://127.0.0.1:8000/docs")
        print("前端:  http://127.0.0.1:8501")
        print("按 Ctrl+C 停止。")

        while True:
            if backend.poll() is not None:
                print("后端进程已退出。")
                return 1
            if frontend.poll() is not None:
                print("前端进程已退出。")
                return 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务…")
        return 0
    finally:
        _terminate(frontend)
        _terminate(backend)


if __name__ == "__main__":
    raise SystemExit(main())
