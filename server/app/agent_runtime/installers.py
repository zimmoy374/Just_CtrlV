from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .workspace import WORKSPACE_DIR, resolve_workspace_root


BEGIN_MARKER = "<!-- second-brain:start -->"
END_MARKER = "<!-- second-brain:end -->"


AGENT_BLOCK = f"""{BEGIN_MARKER}
## second brain 接力入口

进入这个仓库后，先读取当前工作状态：

```powershell
python second_brain.py resume
```

需要确认本地状态是否健康时：

```powershell
python second_brain.py doctor --json
```

没有活跃工作时创建：

```powershell
python second_brain.py start --goal "用户让你完成的目标" --agent "你的 agent 名称"
```

工作中每完成一个有意义的阶段，记录进度：

```powershell
python second_brain.py note --summary "这一步做了什么" --done "已完成事项" --next "下一步" --file "改动文件" --agent "你的 agent 名称"
```

交给另一个 agent 前保存阶段快照：

```powershell
python second_brain.py checkpoint --title "阶段摘要" --summary "当前状态、关键决策、下一步"
```

原则：

- `resume` 是接手工作的入口。
- `doctor` 是诊断数据库、工作区绑定和活跃任务的入口。
- `note` 只记录工作状态，不写正式长期记忆。
- 默认 capability profile 是 `work`；需要读取 profile/private/sensitive 内容时必须显式声明。
- 正式长期记忆只能通过记忆审查台接受待审记忆后进入。
- 不要直接读取或修改 `.data/second_brain.sqlite`。
{END_MARKER}
"""


CLAUDE_BLOCK = f"""{BEGIN_MARKER}
## second brain 接力入口

开始工作前先运行：

```bash
python second_brain.py resume
```

如果接力失败或状态不清楚，运行：

```bash
python second_brain.py doctor --json
```

阶段完成后运行：

```bash
python second_brain.py note --summary "这一步做了什么" --done "已完成事项" --next "下一步" --agent "claude-code"
```

停止或交接前运行：

```bash
python second_brain.py checkpoint --title "阶段摘要" --summary "当前状态、关键决策、下一步"
```

不要把工作事件直接写成正式长期记忆；需要长期保存的内容只能提交为待审记忆。默认 capability profile 是 `work`，不要主动扩大读取范围，除非用户明确要求。
{END_MARKER}
"""


def install_agent_target(root: str | Path | None, target: str) -> dict[str, Any]:
    resolved = resolve_workspace_root(root)
    target = target.strip().lower()
    if target not in {"codex", "claude-code", "opencli", "all"}:
        raise ValueError("install-agent target 必须是 codex、claude-code、opencli 或 all")

    results: list[dict[str, Any]] = []
    if target in {"codex", "all"}:
        results.append(_write_marked_file(resolved / "AGENTS.md", AGENT_BLOCK))
    if target in {"claude-code", "all"}:
        results.append(_write_marked_file(resolved / "CLAUDE.md", CLAUDE_BLOCK))
        results.append(_write_claude_hook_example(resolved))
    if target in {"opencli", "all"}:
        results.append(_write_opencli_descriptor(resolved))
    return {"ok": True, "target": target, "files": results}


def _write_marked_file(path: Path, block: str) -> dict[str, Any]:
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    if BEGIN_MARKER in original and END_MARKER in original:
        before, rest = original.split(BEGIN_MARKER, 1)
        _, after = rest.split(END_MARKER, 1)
        next_text = before.rstrip() + "\n\n" + block.rstrip() + "\n" + after.lstrip()
        action = "updated"
    elif original.strip():
        next_text = original.rstrip() + "\n\n" + block.rstrip() + "\n"
        action = "appended"
    else:
        next_text = block.rstrip() + "\n"
        action = "created"
    path.write_text(next_text, encoding="utf-8")
    return {"path": str(path), "action": action}


def _write_opencli_descriptor(root: Path) -> dict[str, Any]:
    path = root / WORKSPACE_DIR / "opencli.second-brain.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": "second brain",
        "description": "恢复和记录跨 agent 工作状态的本地记忆入口。",
        "commands": [
            {"name": "resume_work", "command": "python second_brain.py resume --json"},
            {"name": "doctor", "command": "python second_brain.py doctor --json"},
            {"name": "record_progress", "command": "python second_brain.py note --json --summary <summary>"},
            {"name": "checkpoint_work", "command": "python second_brain.py checkpoint --json --title <title> --summary <summary>"},
            {"name": "capabilities", "command": "python second_brain.py capabilities --json"},
            {"name": "search_memory", "command": "python second_brain.py tools --json"},
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"path": str(path), "action": "created"}


def _write_claude_hook_example(root: Path) -> dict[str, Any]:
    path = root / WORKSPACE_DIR / "claude-hooks.example.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "hooks": {
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python second_brain.py note --summary \"Claude Code 停止前记录阶段状态\" --agent \"claude-code\"",
                        },
                    ],
                },
            ],
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"path": str(path), "action": "created"}
