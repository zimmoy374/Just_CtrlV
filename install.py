from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(command: list[str], cwd: Path = ROOT) -> None:
    print(f"> {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        print("没有找到 npm。请先安装 Node.js: https://nodejs.org/")
        raise SystemExit(1)

    if not VENV_PYTHON.exists():
        run([sys.executable, "-m", "venv", str(VENV_DIR)])

    run([str(VENV_PYTHON), "-m", "pip", "install", "-r", "requirements.txt"])
    run([npm, "install", "--prefix", "client"])

    if not (ROOT / ".env").exists() and (ROOT / ".env.example").exists():
        shutil.copyfile(ROOT / ".env.example", ROOT / ".env")
        print("已创建 .env，请按你的模型服务填写 OPENAI_API_KEY 或 GEMINI_API_KEY。")

    print("")
    print("安装完成。以后直接双击 run.py，或运行 python run.py。")


if __name__ == "__main__":
    main()
