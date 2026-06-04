from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SECOND_BRAIN_DATA_DIR"] = str(tmp_path / "data")
    env["OPENAI_API_KEY"] = ""
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, str(ROOT_DIR / "second_brain.py"), *args],
        cwd=ROOT_DIR,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )


def test_note_and_checkpoint_quiet_mode_stays_silent_but_json_still_works(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    started = run_cli(
        tmp_path,
        "start",
        "--goal",
        "CLI quiet mode regression",
        "--agent",
        "pytest-agent",
        "--workspace",
        str(workspace),
        "--json",
    )
    assert json.loads(started.stdout)["userGoal"] == "CLI quiet mode regression"

    quiet_note = run_cli(
        tmp_path,
        "note",
        "--summary",
        "quiet note",
        "--done",
        "quiet note recorded",
        "--workspace",
        str(workspace),
        "--quiet",
    )
    assert quiet_note.stdout == ""
    assert quiet_note.stderr == ""

    quiet_checkpoint = run_cli(
        tmp_path,
        "checkpoint",
        "--title",
        "quiet checkpoint",
        "--summary",
        "quiet checkpoint recorded",
        "--workspace",
        str(workspace),
        "--quiet",
    )
    assert quiet_checkpoint.stdout == ""
    assert quiet_checkpoint.stderr == ""

    json_note = run_cli(
        tmp_path,
        "note",
        "--summary",
        "quiet json note",
        "--workspace",
        str(workspace),
        "--quiet",
        "--json",
    )
    note_payload = json.loads(json_note.stdout)
    assert note_payload["ok"] is True
    assert note_payload["eventId"]

    json_checkpoint = run_cli(
        tmp_path,
        "checkpoint",
        "--title",
        "quiet json checkpoint",
        "--summary",
        "quiet json checkpoint recorded",
        "--workspace",
        str(workspace),
        "--quiet",
        "--json",
    )
    checkpoint_payload = json.loads(json_checkpoint.stdout)
    assert checkpoint_payload["ok"] is True
    assert checkpoint_payload["checkpointId"]
