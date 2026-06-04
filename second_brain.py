from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlmodel import Session

from server.app.agent_runtime.installers import install_agent_target
from server.app.agent_runtime.capabilities import list_capability_profiles
from server.app.agent_runtime.workspace import bound_task_id, read_workspace_state, write_workspace_state
from server.app.database import engine, init_db
from server.app.settings import settings
from server.app.models import TaskSession
from server.app.system.status import collect_system_status
from server.app.tasks.checkpoints import create_task_checkpoint
from server.app.tasks.events import append_task_event
from server.app.tasks.handoff import preview_handoff_pack
from server.app.tasks.sessions import ACTIVE_TASK_SESSION_STATUSES, create_task_session, get_task_session, list_task_sessions
from server.app.tasks.state import get_or_create_task_state, update_task_state


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="second_brain.py",
        description="second brain agent-native 工作记忆 CLI。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="创建新的工作会话。")
    start_parser.add_argument("--goal", required=True, help="用户目标。")
    start_parser.add_argument("--title", default="", help="工作会话标题，默认从目标截取。")
    start_parser.add_argument("--agent", default="agent", help="当前 agent 名称。")
    start_parser.add_argument("--json", action="store_true", help="输出 JSON。")
    add_workspace_argument(start_parser)

    resume_parser = subparsers.add_parser("resume", help="读取当前工作状态，供另一个 agent 接力。")
    resume_parser.add_argument("--task-id", default="", help="指定工作会话 ID；默认读取最近活跃会话。")
    resume_parser.add_argument("--json", action="store_true", help="输出 JSON。")
    resume_parser.add_argument("--include-closed", action="store_true", help="允许读取已关闭会话。")
    add_workspace_argument(resume_parser)

    note_parser = subparsers.add_parser("note", help="记录进度并更新当前工作状态。")
    note_parser.add_argument("--summary", required=True, help="本次进展摘要。")
    note_parser.add_argument("--type", default="agent_action", help="事件类型，默认 agent_action。")
    note_parser.add_argument("--task-id", default="", help="指定工作会话 ID；默认读取最近活跃会话。")
    note_parser.add_argument("--goal", default="", help="没有活跃会话时，用这个目标自动创建。")
    note_parser.add_argument("--title", default="", help="自动创建会话时使用的标题。")
    note_parser.add_argument("--agent", default="agent", help="当前 agent 名称。")
    note_parser.add_argument("--current-goal", default=None, help="更新当前目标。")
    note_parser.add_argument("--replace", action="store_true", help="替换本次传入的列表字段，而不是追加。")
    note_parser.add_argument("--quiet", action="store_true", help="成功时不输出，适合 agent hook 静默记录。")
    add_list_argument(note_parser, "--done", "追加已完成事项。")
    add_list_argument(note_parser, "--in-progress", "追加进行中事项。")
    add_list_argument(note_parser, "--next", "追加下一步事项。")
    add_list_argument(note_parser, "--question", "追加待确认问题。")
    add_list_argument(note_parser, "--constraint", "追加约束。")
    add_list_argument(note_parser, "--risk", "追加风险。")
    add_list_argument(note_parser, "--decision", "追加决策。")
    add_list_argument(note_parser, "--file", "追加涉及文件。")
    note_parser.add_argument("--json", action="store_true", help="输出 JSON。")
    add_workspace_argument(note_parser)

    checkpoint_parser = subparsers.add_parser("checkpoint", help="保存阶段快照。")
    checkpoint_parser.add_argument("--title", required=True, help="检查点标题。")
    checkpoint_parser.add_argument("--summary", default="", help="检查点摘要。")
    checkpoint_parser.add_argument("--task-id", default="", help="指定工作会话 ID；默认读取最近活跃会话。")
    checkpoint_parser.add_argument("--json", action="store_true", help="输出 JSON。")
    checkpoint_parser.add_argument("--quiet", action="store_true", help="成功时不输出，适合 agent hook 静默记录。")
    add_workspace_argument(checkpoint_parser)

    health_parser = subparsers.add_parser("healthcheck", help="检查 second brain CLI、数据库和当前工作区绑定。")
    health_parser.add_argument("--json", action="store_true", help="输出 JSON。")
    add_workspace_argument(health_parser)

    tools_parser = subparsers.add_parser("tools", help="列出 agent 可用 CLI/MCP 工具。")
    tools_parser.add_argument("--json", action="store_true", help="输出 JSON。")

    doctor_parser = subparsers.add_parser("doctor", help="诊断本地 second brain 运行状态。")
    doctor_parser.add_argument("--json", action="store_true", help="输出 JSON。")
    add_workspace_argument(doctor_parser)

    capabilities_parser = subparsers.add_parser("capabilities", help="列出本地 agent capability profile。")
    capabilities_parser.add_argument("--json", action="store_true", help="输出 JSON。")

    demo_parser = subparsers.add_parser("demo", help="输出跨 agent 接力演示脚本。")
    demo_parser.add_argument("--json", action="store_true", help="输出 JSON。")

    install_parser = subparsers.add_parser("install-agent", help="为外部 agent 生成或更新接力入口。")
    install_parser.add_argument("--target", required=True, choices=["codex", "claude-code", "opencli", "all"], help="目标 agent。")
    install_parser.add_argument("--json", action="store_true", help="输出 JSON。")
    add_workspace_argument(install_parser)

    args = parser.parse_args()
    init_db()
    with Session(engine) as session:
        if args.command == "start":
            handle_start(session, args)
        elif args.command == "resume":
            handle_resume(session, args)
        elif args.command == "note":
            handle_note(session, args)
        elif args.command == "checkpoint":
            handle_checkpoint(session, args)
        elif args.command == "healthcheck":
            handle_healthcheck(session, args)
        elif args.command == "tools":
            handle_tools(args)
        elif args.command == "doctor":
            handle_doctor(session, args)
        elif args.command == "capabilities":
            handle_capabilities(args)
        elif args.command == "demo":
            handle_demo(args)
        elif args.command == "install-agent":
            handle_install_agent(args)


def add_list_argument(parser: argparse.ArgumentParser, name: str, help_text: str) -> None:
    parser.add_argument(name, action="append", default=None, help=f"{help_text} 可重复传入。")


def add_workspace_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", default="", help="工作区根目录，默认当前目录。")


def handle_start(session: Session, args: argparse.Namespace) -> None:
    title = args.title.strip() or _title_from_goal(args.goal)
    task = create_task_session(session, title=title, user_goal=args.goal, active_agent=args.agent)
    session.commit()
    workspace = write_workspace_state(_workspace_arg(args), task=task, agent=args.agent)
    payload = _task_payload(session, task)
    payload["workspace"] = workspace
    emit(payload, as_json=args.json)


def handle_resume(session: Session, args: argparse.Namespace) -> None:
    task = resolve_task(session, args.task_id, include_closed=args.include_closed, workspace_root=_workspace_arg(args))
    if not task:
        message = "当前工作区没有绑定的活跃工作会话。先运行：python second_brain.py start --goal \"你的目标\"，或显式传入 --task-id。"
        actions = [
            {
                "label": "start_work",
                "command": "python second_brain.py start --goal \"你的目标\" --agent \"你的 agent 名称\"",
                "reason": "当前工作区还没有可接力的活跃任务。",
            },
            {
                "label": "doctor",
                "command": "python second_brain.py doctor --json",
                "reason": "检查工作区绑定、数据库和活跃任务状态。",
            },
        ]
        if args.json:
            emit({"ok": False, "message": message, "nextRecommendedActions": actions}, as_json=True)
            return
        print(message)
        raise SystemExit(1)

    pack, content, budget = preview_handoff_pack(
        session,
        task,
        handoff_format="json" if args.json else "markdown",
        include_closed=args.include_closed,
    )
    session.commit()
    workspace = write_workspace_state(_workspace_arg(args), task=task)
    if args.json:
        emit({"ok": True, "task": _task_payload(session, task), "pack": pack, "budget": budget, "workspace": workspace}, as_json=True)
        return
    print(content.rstrip())


def handle_note(session: Session, args: argparse.Namespace) -> None:
    task = resolve_task(session, args.task_id, workspace_root=_workspace_arg(args))
    if not task:
        if not args.goal.strip():
            raise SystemExit("没有活跃工作会话。请传入 --goal 自动创建，或先运行 start。")
        task = create_task_session(
            session,
            title=args.title.strip() or _title_from_goal(args.goal),
            user_goal=args.goal,
            active_agent=args.agent,
        )

    if args.agent.strip():
        task.active_agent = args.agent.strip()
        session.add(task)

    event = append_task_event(
        session,
        task,
        event_type=args.type,
        summary=args.summary,
        payload={"caller": args.agent},
    )
    state = get_or_create_task_state(session, task.id, current_goal=task.user_goal)
    update_task_state(
        session,
        task.id,
        current_goal=args.current_goal,
        done=merge_or_replace_list(state.done_json, args.done, replace=args.replace),
        in_progress=merge_or_replace_list(state.in_progress_json, args.in_progress, replace=args.replace),
        next_steps=merge_or_replace_list(state.next_steps_json, args.next, replace=args.replace),
        open_questions=merge_or_replace_list(state.open_questions_json, args.question, replace=args.replace),
        constraints=merge_or_replace_list(state.constraints_json, args.constraint, replace=args.replace),
        risks=merge_or_replace_list(state.risks_json, args.risk, replace=args.replace),
        decisions=merge_or_replace_list(state.decisions_json, args.decision, replace=args.replace),
        files_touched=merge_or_replace_list(state.files_touched_json, args.file, replace=args.replace),
    )
    session.commit()
    workspace = write_workspace_state(_workspace_arg(args), task=task, agent=args.agent)
    payload = {"ok": True, "eventId": event.id, "task": _task_payload(session, task), "workspace": workspace}
    if args.quiet and not args.json:
        return
    if not args.json:
        print(f"已记录当前阶段状态：{event.summary}")
        return
    emit(payload, as_json=args.json)


def handle_checkpoint(session: Session, args: argparse.Namespace) -> None:
    task = resolve_task(session, args.task_id, workspace_root=_workspace_arg(args))
    if not task:
        raise SystemExit("没有活跃工作会话。先运行：python second_brain.py start --goal \"你的目标\"")
    checkpoint = create_task_checkpoint(session, task, title=args.title, summary=args.summary)
    session.commit()
    payload = {
        "ok": True,
        "checkpointId": checkpoint.id,
        "task": _task_payload(session, task),
        "workspace": write_workspace_state(_workspace_arg(args), task=task),
    }
    if args.quiet and not args.json:
        return
    if not args.json:
        print(f"已保存阶段快照：{checkpoint.title}")
        return
    emit(payload, as_json=args.json)


def handle_healthcheck(session: Session, args: argparse.Namespace) -> None:
    task = resolve_task(session, "", include_closed=True, workspace_root=_workspace_arg(args))
    payload = {
        "ok": True,
        "databaseUrl": settings.database_url,
        "workspace": read_workspace_state(_workspace_arg(args)),
        "activeTask": _task_payload(session, task) if task else None,
        "commands": [item["name"] for item in cli_tools()],
    }
    emit(payload, as_json=args.json)


def handle_doctor(session: Session, args: argparse.Namespace) -> None:
    workspace = read_workspace_state(_workspace_arg(args))
    task = resolve_task(session, "", include_closed=True, workspace_root=_workspace_arg(args))
    status = collect_system_status(session)
    checks = [
        {"name": "database", "ok": bool(status["storage"]["dataDirExists"]), "detail": status["storage"]["databaseUrl"]},
        {"name": "workspaceBinding", "ok": bool(workspace.get("activeTaskId")), "detail": workspace.get("activeTaskId") or "当前工作区尚未绑定任务"},
        {"name": "activeTask", "ok": bool(task), "detail": task.title if task else "未找到绑定任务"},
        {"name": "pendingAnalysisJobs", "ok": status["analysisJobs"]["running"] == 0, "detail": str(status["analysisJobs"])},
        {"name": "pendingMemoryReview", "ok": True, "detail": f"{status['memory']['pendingProposals']} 个待审记忆"},
    ]
    payload = {
        "ok": all(check["ok"] for check in checks if check["name"] in {"database"}),
        "checks": checks,
        "workspace": workspace,
        "system": status,
        "nextCommands": [
            "python second_brain.py resume",
            "python second_brain.py tools --json",
            "python second_brain_mcp.py",
        ],
    }
    emit(payload, as_json=args.json)


def handle_tools(args: argparse.Namespace) -> None:
    payload = {"ok": True, "cli": cli_tools(), "mcp": mcp_tools()}
    emit(payload, as_json=args.json)


def handle_capabilities(args: argparse.Namespace) -> None:
    emit({"ok": True, "profiles": list_capability_profiles()}, as_json=args.json)


def handle_demo(args: argparse.Namespace) -> None:
    steps = [
        {"actor": "agent A", "command": "python second_brain.py start --goal \"实现一个功能\" --agent codex"},
        {"actor": "agent A", "command": "python second_brain.py note --summary \"完成模型和测试\" --done \"核心模型完成\" --next \"换 agent 继续接 API\" --agent codex"},
        {"actor": "agent A", "command": "python second_brain.py checkpoint --title \"模型完成\" --summary \"下一步接 API 并跑测试\""},
        {"actor": "agent B", "command": "python second_brain.py resume"},
        {"actor": "agent B", "command": "python second_brain.py note --summary \"接手并完成 API\" --done \"API 完成\" --agent claude-code"},
        {"actor": "支持 MCP 的 agent", "command": "python second_brain_mcp.py，然后调用 resume_work/search_memory/record_progress"},
    ]
    payload = {"ok": True, "title": "跨 agent 接力演示", "steps": steps}
    if args.json:
        emit(payload, as_json=True)
        return
    print("# 跨 agent 接力演示\n")
    for index, step in enumerate(steps, start=1):
        print(f"{index}. {step['actor']}")
        print(f"   {step['command']}")


def handle_install_agent(args: argparse.Namespace) -> None:
    payload = install_agent_target(_workspace_arg(args), args.target)
    emit(payload, as_json=args.json)


def resolve_task(
    session: Session,
    task_id: str = "",
    *,
    include_closed: bool = False,
    workspace_root: str | Path | None = None,
) -> TaskSession | None:
    if task_id:
        return get_task_session(session, task_id)
    bound_id = bound_task_id(workspace_root)
    if bound_id:
        task = get_task_session(session, bound_id)
        if task and (include_closed or task.status in ACTIVE_TASK_SESSION_STATUSES):
            return task
    return None


def merge_list(existing: list[str] | None, additions: list[str] | None) -> list[str] | None:
    if additions is None:
        return None
    merged = list(existing or [])
    for value in additions:
        clean = str(value).strip()
        if clean and clean not in merged:
            merged.append(clean)
    return merged


def merge_or_replace_list(existing: list[str] | None, additions: list[str] | None, *, replace: bool = False) -> list[str] | None:
    if additions is None:
        return None
    if replace:
        return list(additions)
    return merge_list(existing, additions)


def _task_payload(session: Session, task: TaskSession) -> dict[str, Any]:
    state = get_or_create_task_state(session, task.id, current_goal=task.user_goal)
    return {
        "id": task.id,
        "title": task.title,
        "userGoal": task.user_goal,
        "status": task.status,
        "activeAgent": task.active_agent,
        "updatedAt": task.updated_at.isoformat(),
        "currentGoal": state.current_goal,
        "done": state.done_json or [],
        "inProgress": state.in_progress_json or [],
        "nextSteps": state.next_steps_json or [],
        "openQuestions": state.open_questions_json or [],
        "decisions": state.decisions_json or [],
        "risks": state.risks_json or [],
        "filesTouched": state.files_touched_json or [],
    }


def _title_from_goal(goal: str) -> str:
    title = " ".join(goal.split())
    return title[:48] or "未命名工作"


def _workspace_arg(args: argparse.Namespace) -> str | None:
    return args.workspace.strip() or None


def cli_tools() -> list[dict[str, str]]:
    return [
        {"name": "resume", "command": "python second_brain.py resume --json", "purpose": "恢复当前工作状态。"},
        {"name": "start", "command": "python second_brain.py start --goal \"...\" --json", "purpose": "创建新的工作会话并绑定当前工作区。"},
        {"name": "note", "command": "python second_brain.py note --summary \"...\" --json", "purpose": "记录阶段进展并更新当前工作状态。"},
        {"name": "checkpoint", "command": "python second_brain.py checkpoint --title \"...\" --summary \"...\" --json", "purpose": "保存阶段快照。"},
        {"name": "quiet-note", "command": "python second_brain.py note --summary \"...\" --quiet", "purpose": "后台静默记录阶段进展，不打扰用户。"},
        {"name": "quiet-checkpoint", "command": "python second_brain.py checkpoint --title \"...\" --summary \"...\" --quiet", "purpose": "后台静默保存阶段快照。"},
        {"name": "healthcheck", "command": "python second_brain.py healthcheck --json", "purpose": "检查数据库、工作区绑定和可用命令。"},
        {"name": "doctor", "command": "python second_brain.py doctor --json", "purpose": "诊断本地运行状态、工作区绑定和恢复入口。"},
        {"name": "capabilities", "command": "python second_brain.py capabilities --json", "purpose": "列出 agent capability profile。"},
        {"name": "demo", "command": "python second_brain.py demo", "purpose": "输出跨 agent 接力演示脚本。"},
        {"name": "install-agent", "command": "python second_brain.py install-agent --target all --json", "purpose": "生成或更新多 agent 接力入口。"},
        {"name": "mcp-server", "command": "python second_brain_mcp.py", "purpose": "启动本地 MCP stdio 服务器。"},
    ]


def mcp_tools() -> list[dict[str, str]]:
    return [
        {"name": "resume_work", "purpose": "恢复当前工作状态。"},
        {"name": "record_progress", "purpose": "记录阶段进展，不写正式长期记忆。"},
        {"name": "checkpoint_work", "purpose": "保存阶段快照。"},
        {"name": "search_memory", "purpose": "按预算检索正式知识 ContextPack。"},
        {"name": "read_evidence", "purpose": "按 ref 读取预算化证据摘录。"},
        {"name": "propose_memory", "purpose": "创建待审记忆，等待用户审查。"},
    ]


def emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
