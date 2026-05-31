from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from ..models import TaskSession, utc_now


WORKSPACE_DIR = ".second-brain"
WORKSPACE_FILE = "workspace.json"


def resolve_workspace_root(root: str | Path | None = None) -> Path:
    return Path(root or Path.cwd()).resolve()


def workspace_state_path(root: str | Path | None = None) -> Path:
    return resolve_workspace_root(root) / WORKSPACE_DIR / WORKSPACE_FILE


def workspace_id(root: str | Path | None = None) -> str:
    resolved = str(resolve_workspace_root(root)).replace("\\", "/").lower()
    return str(uuid5(NAMESPACE_URL, f"second-brain:{resolved}"))


def read_workspace_state(root: str | Path | None = None) -> dict[str, Any]:
    path = workspace_state_path(root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_workspace_state(
    root: str | Path | None,
    *,
    task: TaskSession | None = None,
    agent: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = resolve_workspace_root(root)
    now = utc_now().isoformat()
    current = read_workspace_state(resolved)
    payload: dict[str, Any] = {
        "workspaceId": current.get("workspaceId") or workspace_id(resolved),
        "workspaceRoot": str(resolved),
        "activeTaskId": current.get("activeTaskId") or "",
        "activeTaskTitle": current.get("activeTaskTitle") or "",
        "lastAgent": agent or current.get("lastAgent") or "",
        "lastHandoffAt": now,
        "updatedAt": now,
    }
    if task is not None:
        payload.update(
            {
                "activeTaskId": task.id,
                "activeTaskTitle": task.title,
                "activeTaskStatus": task.status,
                "activeTaskUpdatedAt": task.updated_at.isoformat(),
            },
        )
    if extra:
        payload.update(extra)

    path = workspace_state_path(resolved)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def bound_task_id(root: str | Path | None = None) -> str:
    return str(read_workspace_state(root).get("activeTaskId") or "").strip()
