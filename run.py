from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:5173"
API_URL = "http://127.0.0.1:8000"
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port(port: int, seconds: int = 20) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if port_is_open(port):
            return True
        time.sleep(0.4)
    return False


def require_ready() -> str:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    missing = []
    if not npm:
        missing.append("Node.js / npm")
    if not VENV_PYTHON.exists():
        missing.append(".venv")
    if not (ROOT / "client" / "node_modules").exists():
        missing.append("client/node_modules")

    if missing:
        print("缺少运行依赖：")
        for item in missing:
            print(f"- {item}")
        print("")
        print("第一次使用先运行：")
        print("python install.py")
        raise SystemExit(1)

    return npm


def main() -> None:
    npm = require_ready()

    if port_is_open(5173) and port_is_open(8000):
        print("应用已经在运行，正在打开浏览器...")
        webbrowser.open(URL)
        return

    backend = subprocess.Popen(
        [
            str(VENV_PYTHON),
            "-m",
            "uvicorn",
            "server.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--no-access-log",
        ],
        cwd=ROOT,
    )
    frontend = subprocess.Popen(
        [npm, "--prefix", "client", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"],
        cwd=ROOT,
    )

    print("正在启动随心一记...")
    if wait_for_port(5173) and wait_for_port(8000):
        print(f"随心一记：{URL}")
        webbrowser.open(URL)
    else:
        print("启动超时。请检查上方终端日志。")

    try:
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n正在停止服务...")
    finally:
        for process in (frontend, backend):
            if process.poll() is None:
                process.terminate()


if __name__ == "__main__":
    main()
