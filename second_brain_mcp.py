from __future__ import annotations

import json
import sys
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from second_brain import _task_payload, merge_list, resolve_task
from server.app.agent_runtime.capabilities import list_capability_profiles, resolve_capabilities
from server.app.agent_runtime.workspace import write_workspace_state
from server.app.database import engine, init_db
from server.app.memory_kernel.proposals import create_memory_proposal
from server.app.models import TaskSession
from server.app.routes.agent import get_agent_context_pack_api, get_agent_source_excerpt_api
from server.app.tasks.checkpoints import create_task_checkpoint
from server.app.tasks.events import append_task_event
from server.app.tasks.handoff import preview_handoff_pack
from server.app.tasks.sessions import create_task_session
from server.app.tasks.state import get_or_create_task_state, update_task_state


PROTOCOL_VERSION = "2024-11-05"


TOOLS = [
    {
        "name": "resume_work",
        "description": "恢复当前工作状态，返回压缩 handoff。优先读取当前工作区绑定的活跃任务。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "taskId": {"type": "string"},
                "includeClosed": {"type": "boolean"},
                "workspace": {"type": "string"},
            },
        },
    },
    {
        "name": "record_progress",
        "description": "记录阶段进展并更新当前工作状态；不会写入正式长期记忆。",
        "inputSchema": {
            "type": "object",
            "required": ["summary"],
            "properties": {
                "summary": {"type": "string"},
                "goal": {"type": "string"},
                "title": {"type": "string"},
                "agent": {"type": "string"},
                "taskId": {"type": "string"},
                "currentGoal": {"type": "string"},
                "done": {"type": "array", "items": {"type": "string"}},
                "inProgress": {"type": "array", "items": {"type": "string"}},
                "nextSteps": {"type": "array", "items": {"type": "string"}},
                "openQuestions": {"type": "array", "items": {"type": "string"}},
                "constraints": {"type": "array", "items": {"type": "string"}},
                "risks": {"type": "array", "items": {"type": "string"}},
                "decisions": {"type": "array", "items": {"type": "string"}},
                "filesTouched": {"type": "array", "items": {"type": "string"}},
                "replaceState": {"type": "boolean"},
                "workspace": {"type": "string"},
            },
        },
    },
    {
        "name": "checkpoint_work",
        "description": "保存阶段快照，供另一个 agent 接力。",
        "inputSchema": {
            "type": "object",
            "required": ["title"],
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "taskId": {"type": "string"},
                "workspace": {"type": "string"},
            },
        },
    },
    {
        "name": "search_memory",
        "description": "按预算检索正式知识 ContextPack，不读取全库。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "caller": {"type": "string"},
                "taskSessionId": {"type": "string"},
                "capabilityProfile": {"type": "string", "enum": sorted(list_capability_profiles().keys())},
                "capabilities": {"type": "array", "items": {"type": "string"}},
                "maxChars": {"type": "integer"},
            },
        },
    },
    {
        "name": "read_evidence",
        "description": "按 source ref 读取预算化原始证据摘录。",
        "inputSchema": {
            "type": "object",
            "required": ["ref"],
            "properties": {
                "ref": {"type": "string"},
                "query": {"type": "string"},
                "caller": {"type": "string"},
                "taskSessionId": {"type": "string"},
                "capabilityProfile": {"type": "string", "enum": sorted(list_capability_profiles().keys())},
                "capabilities": {"type": "array", "items": {"type": "string"}},
                "maxChars": {"type": "integer"},
            },
        },
    },
    {
        "name": "propose_memory",
        "description": "创建待审记忆；不会直接写入正式长期记忆。",
        "inputSchema": {
            "type": "object",
            "required": ["type", "title"],
            "properties": {
                "type": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "targetStore": {"type": "string"},
                "taskSessionId": {"type": "string"},
                "scope": {"type": "string"},
                "evidenceRefs": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
                "reviewNote": {"type": "string"},
            },
        },
    },
]


def main() -> None:
    init_db()
    while True:
        message = _read_message()
        if message is None:
            break
        response = _handle_message(message)
        if response is not None:
            _write_message(response)


def _handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    try:
        if method == "initialize":
            return _result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "second brain", "version": "0.1.0"},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": TOOLS})
        if method == "tools/call":
            params = message.get("params") or {}
            payload = _call_tool(str(params.get("name") or ""), params.get("arguments") or {})
            return _result(request_id, {"content": [{"type": "text", "text": _json_text(payload)}]})
        return _error(request_id, -32601, f"未知 MCP 方法：{method}")
    except Exception as exc:
        return _error(request_id, -32000, str(exc))


def _call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as session:
        if name == "resume_work":
            return _tool_resume(session, args)
        if name == "record_progress":
            return _tool_record_progress(session, args)
        if name == "checkpoint_work":
            return _tool_checkpoint(session, args)
        if name == "search_memory":
            return _tool_search_memory(session, args)
        if name == "read_evidence":
            return _tool_read_evidence(session, args)
        if name == "propose_memory":
            return _tool_propose_memory(session, args)
    raise ValueError(f"未知工具：{name}")


def _tool_resume(session: Session, args: dict[str, Any]) -> dict[str, Any]:
    task = resolve_task(
        session,
        str(args.get("taskId") or ""),
        include_closed=bool(args.get("includeClosed") or False),
        workspace_root=args.get("workspace") or None,
    )
    if not task:
        return {"ok": False, "message": "当前工作区没有绑定的活跃工作会话。请先创建工作，或显式传入 taskId。"}
    pack, content, budget = preview_handoff_pack(session, task, handoff_format="markdown", include_closed=bool(args.get("includeClosed") or False))
    session.commit()
    workspace = write_workspace_state(args.get("workspace") or None, task=task)
    return {"ok": True, "content": content, "pack": pack, "budget": budget, "task": _task_payload(session, task), "workspace": workspace}


def _tool_record_progress(session: Session, args: dict[str, Any]) -> dict[str, Any]:
    task = resolve_task(session, str(args.get("taskId") or ""), workspace_root=args.get("workspace") or None)
    if not task:
        goal = str(args.get("goal") or "").strip()
        if not goal:
            return {"ok": False, "message": "当前工作区没有绑定的活跃工作会话，也没有传入 goal。"}
        task = create_task_session(
            session,
            title=str(args.get("title") or goal[:48] or "未命名工作"),
            user_goal=goal,
            active_agent=str(args.get("agent") or "agent"),
        )
    elif str(args.get("agent") or "").strip():
        task.active_agent = str(args.get("agent")).strip()
        session.add(task)
    event = append_task_event(
        session,
        task,
        event_type="agent_action",
        summary=str(args["summary"]),
        payload={"caller": str(args.get("agent") or "agent")},
    )
    state = get_or_create_task_state(session, task.id, current_goal=task.user_goal)
    update_task_state(
        session,
        task.id,
        current_goal=args.get("currentGoal"),
        done=_merge_or_replace(state.done_json, _list_arg(args, "done"), replace=bool(args.get("replaceState") or False)),
        in_progress=_merge_or_replace(state.in_progress_json, _list_arg(args, "inProgress"), replace=bool(args.get("replaceState") or False)),
        next_steps=_merge_or_replace(state.next_steps_json, _list_arg(args, "nextSteps"), replace=bool(args.get("replaceState") or False)),
        open_questions=_merge_or_replace(state.open_questions_json, _list_arg(args, "openQuestions"), replace=bool(args.get("replaceState") or False)),
        constraints=_merge_or_replace(state.constraints_json, _list_arg(args, "constraints"), replace=bool(args.get("replaceState") or False)),
        risks=_merge_or_replace(state.risks_json, _list_arg(args, "risks"), replace=bool(args.get("replaceState") or False)),
        decisions=_merge_or_replace(state.decisions_json, _list_arg(args, "decisions"), replace=bool(args.get("replaceState") or False)),
        files_touched=_merge_or_replace(state.files_touched_json, _list_arg(args, "filesTouched"), replace=bool(args.get("replaceState") or False)),
    )
    session.commit()
    workspace = write_workspace_state(args.get("workspace") or None, task=task, agent=str(args.get("agent") or "agent"))
    return {"ok": True, "eventId": event.id, "task": _task_payload(session, task), "workspace": workspace}


def _tool_checkpoint(session: Session, args: dict[str, Any]) -> dict[str, Any]:
    task = resolve_task(session, str(args.get("taskId") or ""), workspace_root=args.get("workspace") or None)
    if not task:
        return {"ok": False, "message": "当前工作区没有绑定的活跃工作会话。请先创建工作，或显式传入 taskId。"}
    checkpoint = create_task_checkpoint(session, task, title=str(args["title"]), summary=str(args.get("summary") or ""))
    session.commit()
    workspace = write_workspace_state(args.get("workspace") or None, task=task)
    return {"ok": True, "checkpointId": checkpoint.id, "task": _task_payload(session, task), "workspace": workspace}


def _tool_search_memory(session: Session, args: dict[str, Any]) -> dict[str, Any]:
    try:
        capabilities = _resolve_mcp_capabilities(args)
        response = get_agent_context_pack_api(
            q=str(args.get("query") or ""),
            caller=str(args.get("caller") or "mcp-agent"),
            task_session_id=args.get("taskSessionId") or None,
            scope=None,
            capability_profile=str(args.get("capabilityProfile") or "work"),
            capabilities=capabilities,
            item_limit=int(args.get("itemLimit") or 6),
            page_limit=int(args.get("pageLimit") or 3),
            source_excerpt_limit=int(args.get("sourceExcerptLimit") or 3),
            profile_fact_limit=int(args.get("profileFactLimit") or 5),
            max_chars=int(args.get("maxChars") or 4000),
            session=session,
        )
    except HTTPException as exc:
        return {"ok": False, "error": exc.detail}
    except ValueError as exc:
        return {"ok": False, "error": {"code": "invalid_capability_profile", "message": str(exc), "refs": []}}
    return {"ok": True, "contextPack": response.model_dump(mode="json", by_alias=True)}


def _tool_read_evidence(session: Session, args: dict[str, Any]) -> dict[str, Any]:
    try:
        capabilities = _resolve_mcp_capabilities(args)
        response = get_agent_source_excerpt_api(
            ref=str(args["ref"]),
            q=str(args.get("query") or ""),
            caller=str(args.get("caller") or "mcp-agent"),
            task_session_id=args.get("taskSessionId") or None,
            scope=None,
            capability_profile=str(args.get("capabilityProfile") or "work"),
            capabilities=capabilities,
            max_chars=int(args.get("maxChars") or 800),
            session=session,
        )
    except HTTPException as exc:
        return {"ok": False, "error": exc.detail}
    except ValueError as exc:
        return {"ok": False, "error": {"code": "invalid_capability_profile", "message": str(exc), "refs": []}}
    return {"ok": True, "evidence": response.model_dump(mode="json", by_alias=True)}


def _tool_propose_memory(session: Session, args: dict[str, Any]) -> dict[str, Any]:
    proposal = create_memory_proposal(
        session,
        proposal_type=str(args["type"]),
        title=str(args["title"]),
        body=str(args.get("body") or ""),
        target_store=args.get("targetStore") or None,
        task_session_id=args.get("taskSessionId") or None,
        scope=str(args.get("scope") or "workspace"),
        evidence_refs=_list_arg(args, "evidenceRefs") or [],
        confidence=args.get("confidence"),
        review_note=str(args.get("reviewNote") or "MCP agent 提交待审记忆"),
    )
    session.commit()
    return {
        "ok": True,
        "proposal": {
            "id": proposal.id,
            "status": proposal.status,
            "targetStore": proposal.target_store,
            "type": proposal.type,
            "title": proposal.title,
            "directLongTermWrite": False,
        },
    }


def _list_arg(args: dict[str, Any], key: str) -> list[str] | None:
    value = args.get(key)
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _resolve_mcp_capabilities(args: dict[str, Any]) -> list[str]:
    requested = _list_arg(args, "capabilities")
    return resolve_capabilities(str(args.get("capabilityProfile") or "work"), requested)


def _merge_or_replace(existing: list[str] | None, additions: list[str] | None, *, replace: bool = False) -> list[str] | None:
    if additions is None:
        return None
    if replace:
        return additions
    return merge_list(existing, additions)


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line_text = line.decode("ascii", errors="ignore").strip()
        if not line_text:
            break
        key, _, value = line_text.partition(":")
        headers[key.lower()] = value.strip()
    length = int(headers.get("content-length") or 0)
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def _write_message(message: dict[str, Any]) -> None:
    body = _json_text(message).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
