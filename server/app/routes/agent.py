from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from ..agent_runtime.capabilities import list_capability_profiles, resolve_capabilities
from ..database import get_session
from ..memory_core.composer import MemoryContextComposer
from ..memory_core.context_helpers import excerpt_around
from ..memory_core.decisions import record_provenance_event
from ..memory_core.protocol import MemoryRef
from ..memory_kernel.proposals import create_memory_proposal, list_memory_proposals
from ..models import SourceItem, TaskSession, utc_now
from ..presenters import (
    memory_proposal_to_response,
    task_checkpoint_to_response,
    task_event_to_response,
    task_session_to_response,
    task_state_to_response,
)
from ..schemas import (
    ContextPackResponse,
    MemoryProposalResponse,
    TaskCheckpointCreate,
    TaskCheckpointResponse,
    TaskEventResponse,
    TaskSessionResponse,
    TaskStatePatch,
    TaskStateResponse,
)
from ..tasks.checkpoints import create_task_checkpoint
from ..tasks.events import append_task_event
from ..tasks.handoff import preview_handoff_pack
from ..tasks.sessions import get_task_session, list_task_sessions
from ..tasks.state_machine import ensure_task_mutable
from ..tasks.state import update_task_state


router = APIRouter(prefix="/api/agent", tags=["agent-protocol"])

AGENT_TOOLS = [
    "list_capability_profiles",
    "get_context_pack",
    "get_source_excerpt",
    "list_active_tasks",
    "record_task_event",
    "update_task_state",
    "create_checkpoint",
    "get_handoff_pack",
    "propose_memory",
    "list_memory_proposals",
]


class AgentToolInfo(BaseModel):
    name: str
    method: str
    path: str
    writes: bool
    direct_long_term_write: bool = Field(alias="directLongTermWrite")
    restrictions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class AgentEventCreate(BaseModel):
    caller: str = Field(default="agent")
    type: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    payload: dict = Field(default_factory=dict)
    source_ref: str = Field(default="", alias="sourceRef")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class AgentCheckpointCreate(TaskCheckpointCreate):
    caller: str = Field(default="agent")


class AgentMemoryProposalCreate(BaseModel):
    caller: str = Field(default="agent")
    task_session_id: Optional[str] = Field(default=None, alias="taskSessionId")
    target_store: Optional[str] = Field(default=None, alias="targetStore")
    type: str
    title: str
    body: str = ""
    structured_payload: dict = Field(default_factory=dict, alias="structuredPayload")
    scope: str = "workspace"
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    confidence: Optional[float] = None
    review_note: str = Field(default="", alias="reviewNote")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class AgentSourceExcerptResponse(BaseModel):
    ref: str
    source_item_id: str = Field(alias="sourceItemId")
    title: str
    kind: str
    excerpt: str
    citation_ref: str = Field(alias="citationRef")
    evidence_refs: list[str] = Field(alias="evidenceRefs")
    budget: dict
    warnings: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class AgentHandoffResponse(BaseModel):
    task_session_id: str = Field(alias="taskSessionId")
    format: str
    content: str
    pack: dict
    budget: dict
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Any = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class AgentProtocolInstructions(BaseModel):
    name: str
    purpose: str
    tools_endpoint: str = Field(alias="toolsEndpoint")
    operating_rules: list[str] = Field(alias="operatingRules")
    workflow: list[dict[str, Any]]
    refs: dict[str, str]

    model_config = ConfigDict(populate_by_name=True)


def _agent_protocol_instructions() -> AgentProtocolInstructions:
    return AgentProtocolInstructions(
        name="second brain agent protocol",
        purpose="让外部工具按权限读取个人知识、引用原始证据，并把值得长期保存的内容提交为待审记忆。",
        toolsEndpoint="/api/agent/tools",
        operatingRules=[
            "先读取 /api/agent/instructions，再读取 /api/agent/tools。",
            "读取个人资料、私密或敏感内容时，必须显式声明 capabilityProfile；默认 work 档位不会暴露这些内容。",
            "需要上下文时调用 /api/agent/context，不要尝试全量读取数据库或导出包。",
            "只在 ContextPack 返回 source: 引用后，才调用 /api/agent/source-excerpt 获取证据摘录。",
            "外部工具不能直接写入长期记忆，只能调用 /api/agent/proposals 提交待审记忆。",
            "外部工具不能接受、拒绝、覆盖、删除记忆，也不能解决冲突或清除原始证据。",
            "所有写入都必须带 caller；涉及具体任务时带 taskSessionId 或 task: scope。",
        ],
        workflow=[
            {
                "step": "发现协议",
                "call": "GET /api/agent/instructions",
                "result": "了解规则、引用格式和推荐调用顺序。",
            },
            {
                "step": "发现工具",
                "call": "GET /api/agent/tools",
                "result": "获得可调用端点、写入边界和限制。",
            },
            {
                "step": "确认权限档位",
                "call": "GET /api/agent/capabilities",
                "result": "选择 work/profile/private/sensitive/trusted 之一，再按需请求具体 capability。",
            },
            {
                "step": "读取上下文",
                "call": "GET /api/agent/context?q=...&caller=...&capabilityProfile=work&maxChars=...",
                "result": "获得预算化 ContextPack、引用、证据 refs 和 warnings。",
            },
            {
                "step": "读取证据",
                "call": "GET /api/agent/source-excerpt?ref=source:...&q=...",
                "result": "只拿与当前问题相关的原始证据摘录。",
            },
            {
                "step": "提交待审记忆",
                "call": "POST /api/agent/proposals",
                "result": "创建 pending proposal，等待用户在记忆审查台决定是否进入长期记忆。",
            },
        ],
        refs={
            "source": "source:<id>，原始证据引用",
            "item": "item:<id>，正式知识条目引用",
            "page": "page:<id>，知识页引用",
            "fact": "fact:<id>，动态事实引用",
            "task": "task:<id>，外部工具任务作用域引用",
        },
    )


@router.get("", response_model=AgentProtocolInstructions)
def get_agent_protocol_entry_api() -> AgentProtocolInstructions:
    return _agent_protocol_instructions()


@router.get("/instructions", response_model=AgentProtocolInstructions)
def get_agent_protocol_instructions_api() -> AgentProtocolInstructions:
    return _agent_protocol_instructions()


@router.get("/tools", response_model=list[AgentToolInfo])
def list_agent_tools_api() -> list[AgentToolInfo]:
    specs = {
        "list_capability_profiles": ("GET", "/api/agent/capabilities"),
        "get_context_pack": ("GET", "/api/agent/context"),
        "get_source_excerpt": ("GET", "/api/agent/source-excerpt"),
        "list_active_tasks": ("GET", "/api/agent/tasks"),
        "record_task_event": ("POST", "/api/agent/tasks/{task_id}/events"),
        "update_task_state": ("PATCH", "/api/agent/tasks/{task_id}/state"),
        "create_checkpoint": ("POST", "/api/agent/tasks/{task_id}/checkpoints"),
        "get_handoff_pack": ("GET", "/api/agent/tasks/{task_id}/handoff"),
        "propose_memory": ("POST", "/api/agent/proposals"),
        "list_memory_proposals": ("GET", "/api/agent/proposals"),
    }
    writing_tools = {"record_task_event", "update_task_state", "create_checkpoint", "propose_memory"}
    restrictions = {
        "list_capability_profiles": ["只返回本地权限档位说明，不授予远程安全权限。"],
        "propose_memory": ["只能创建待审记忆；不暴露接受、解决冲突、失效事实或删除证据的能力。"],
        "get_context_pack": ["按预算和范围过滤；永远不返回全库内容。"],
        "get_source_excerpt": ["必须提供 source 引用；读取私密、个人资料或敏感证据需要显式能力。"],
        "get_handoff_pack": ["只返回预览；过期或已关闭任务会明确提示。"],
    }
    return [
        AgentToolInfo(
            name=name,
            method=specs[name][0],
            path=specs[name][1],
            writes=name in writing_tools,
            directLongTermWrite=False,
            restrictions=restrictions.get(name, []),
        )
        for name in AGENT_TOOLS
    ]


@router.get("/capabilities")
def list_agent_capabilities_api() -> dict[str, Any]:
    return {
        "defaultProfile": "work",
        "profiles": list_capability_profiles(),
        "note": "capabilityProfile 是本地 agent 调用档位，用来避免误读私密内容；它不是网络鉴权系统。",
    }


@router.get("/context", response_model=ContextPackResponse)
def get_agent_context_pack_api(
    q: str = "",
    caller: str = Query("agent"),
    task_session_id: str | None = Query(default=None, alias="taskSessionId"),
    scope: str | None = Query(default=None),
    capability_profile: str | None = Query(default=None, alias="capabilityProfile"),
    capabilities: list[str] | None = Query(default=None, alias="capability"),
    item_limit: int = Query(6, alias="itemLimit", ge=1, le=20),
    page_limit: int = Query(3, alias="pageLimit", ge=0, le=10),
    source_excerpt_limit: int = Query(3, alias="sourceExcerptLimit", ge=0, le=5),
    profile_fact_limit: int = Query(5, alias="profileFactLimit", ge=0, le=10),
    max_chars: int = Query(4000, alias="maxChars", le=12000),
    session: Session = Depends(get_session),
) -> ContextPackResponse:
    if max_chars < 500:
        raise _agent_http_error(413, "budget_exceeded", "ContextPack 的 maxChars 至少为 500。")
    _validate_scope(session, task_session_id=task_session_id, scope=scope)
    resolved_capabilities = _resolve_agent_capabilities(capability_profile, capabilities)
    pack = MemoryContextComposer().build_context_pack(
        session,
        query=q,
        task_session_id=task_session_id,
        scope=scope,
        capabilities=resolved_capabilities,
        max_pages=page_limit,
        max_items=item_limit,
        max_source_excerpts=source_excerpt_limit,
        max_profile_facts=profile_fact_limit,
        max_chars=max_chars,
    )
    if pack["budget"]["truncated"]:
        pack["warnings"].append(
            _agent_warning(
                "budget_exceeded",
                "warning",
                f"ContextPack 已为调用方 {caller} 截断；请缩小查询词或提高 maxChars。",
            ),
        )
    _audit_agent_tool_call(
        session,
        tool_name="get_context_pack",
        caller=caller,
        task_session_id=task_session_id,
        scope=scope,
        refs=_context_refs(pack),
        budget=pack["budget"],
        warnings=pack["warnings"],
        capability_profile=capability_profile,
        capabilities=resolved_capabilities,
    )
    session.commit()
    return ContextPackResponse.model_validate(pack)


@router.get("/source-excerpt", response_model=AgentSourceExcerptResponse)
def get_agent_source_excerpt_api(
    ref: str,
    caller: str = Query("agent"),
    q: str = "",
    task_session_id: str | None = Query(default=None, alias="taskSessionId"),
    scope: str | None = Query(default=None),
    capability_profile: str | None = Query(default=None, alias="capabilityProfile"),
    capabilities: list[str] | None = Query(default=None, alias="capability"),
    max_chars: int = Query(800, alias="maxChars", le=2000),
    session: Session = Depends(get_session),
) -> AgentSourceExcerptResponse:
    if max_chars < 80:
        raise _agent_http_error(413, "budget_exceeded", "证据摘录的 maxChars 至少为 80。", refs=[ref])
    _validate_scope(session, task_session_id=task_session_id, scope=scope)
    resolved_capabilities = _resolve_agent_capabilities(capability_profile, capabilities)
    source_item = _source_item_from_ref(session, ref)
    _ensure_source_visible(source_item, task_session_id=task_session_id, scope=scope, capabilities=resolved_capabilities)
    excerpt = excerpt_around(source_item.content_text or "", q, limit=max_chars)
    truncated = len(" ".join((source_item.content_text or "").split())) > len(excerpt)
    warnings = [_agent_warning("budget_exceeded", "warning", "证据摘录已按 maxChars 截断。")] if truncated else []
    source_ref = f"source:{source_item.id}"
    budget = {"maxChars": max_chars, "usedChars": len(excerpt), "truncated": truncated}
    _audit_agent_tool_call(
        session,
        tool_name="get_source_excerpt",
        caller=caller,
        task_session_id=task_session_id,
        scope=scope,
        refs=[source_ref],
        to_ref=source_ref,
        budget=budget,
        warnings=warnings,
        capability_profile=capability_profile,
        capabilities=resolved_capabilities,
    )
    session.commit()
    return AgentSourceExcerptResponse(
        ref=source_ref,
        sourceItemId=source_item.id,
        title=source_item.title,
        kind=source_item.kind,
        excerpt=excerpt,
        citationRef=source_ref,
        evidenceRefs=[source_ref],
        budget=budget,
        warnings=warnings,
    )


@router.get("/tasks", response_model=list[TaskSessionResponse])
def list_agent_active_tasks_api(
    caller: str = Query("agent"),
    session: Session = Depends(get_session),
) -> list[TaskSessionResponse]:
    tasks = list_task_sessions(session, status="active")
    _audit_agent_tool_call(
        session,
        tool_name="list_active_tasks",
        caller=caller,
        refs=[f"task:{task.id}" for task in tasks],
    )
    session.commit()
    return [task_session_to_response(task) for task in tasks]


@router.post("/tasks/{task_id}/events", response_model=TaskEventResponse)
def record_agent_task_event_api(
    task_id: str,
    payload: AgentEventCreate,
    session: Session = Depends(get_session),
) -> TaskEventResponse:
    task = _require_task(session, task_id)
    _ensure_task_mutable(task)
    try:
        event = append_task_event(
            session,
            task,
            event_type=payload.type,
            summary=payload.summary,
            payload={**payload.payload, "caller": payload.caller},
            source="second_brain",
            source_ref=payload.source_ref,
        )
    except ValueError as exc:
        raise _agent_http_error(400, "invalid_request", str(exc)) from exc
    _audit_agent_tool_call(
        session,
        tool_name="record_task_event",
        caller=payload.caller,
        task_session_id=task.id,
        refs=[payload.source_ref] if payload.source_ref else [],
        to_ref=f"task-event:{event.id}",
        write=True,
    )
    session.commit()
    session.refresh(event)
    return task_event_to_response(event)


@router.patch("/tasks/{task_id}/state", response_model=TaskStateResponse)
def update_agent_task_state_api(
    task_id: str,
    payload: TaskStatePatch,
    caller: str = Query("agent"),
    session: Session = Depends(get_session),
) -> TaskStateResponse:
    task = _require_task(session, task_id)
    _ensure_task_mutable(task)
    state = update_task_state(
        session,
        task_id,
        current_goal=payload.current_goal,
        done=payload.done,
        in_progress=payload.in_progress,
        next_steps=payload.next_steps,
        open_questions=payload.open_questions,
        constraints=payload.constraints,
        risks=payload.risks,
        decisions=payload.decisions,
        files_touched=payload.files_touched,
        confidence=payload.confidence,
    )
    _audit_agent_tool_call(
        session,
        tool_name="update_task_state",
        caller=caller,
        task_session_id=task.id,
        to_ref=f"task:{task.id}",
        write=True,
    )
    session.commit()
    session.refresh(state)
    return task_state_to_response(state)


@router.post("/tasks/{task_id}/checkpoints", response_model=TaskCheckpointResponse)
def create_agent_checkpoint_api(
    task_id: str,
    payload: AgentCheckpointCreate,
    session: Session = Depends(get_session),
) -> TaskCheckpointResponse:
    task = _require_task(session, task_id)
    _ensure_task_mutable(task)
    try:
        checkpoint = create_task_checkpoint(session, task, title=payload.title, summary=payload.summary)
    except ValueError as exc:
        raise _agent_http_error(400, "invalid_request", str(exc)) from exc
    _audit_agent_tool_call(
        session,
        tool_name="create_checkpoint",
        caller=payload.caller,
        task_session_id=task.id,
        to_ref=f"checkpoint:{checkpoint.id}",
        write=True,
    )
    session.commit()
    session.refresh(checkpoint)
    return task_checkpoint_to_response(checkpoint)


@router.get("/tasks/{task_id}/handoff", response_model=AgentHandoffResponse)
def get_agent_handoff_pack_api(
    task_id: str,
    caller: str = Query("agent"),
    format: str = Query("markdown"),
    include_closed: bool = Query(default=False, alias="includeClosed"),
    session: Session = Depends(get_session),
) -> AgentHandoffResponse:
    task = _require_task(session, task_id)
    try:
        pack, content, budget = preview_handoff_pack(session, task, handoff_format=format, include_closed=include_closed)
    except ValueError as exc:
        raise _agent_http_error(409, "stale_task", str(exc), refs=[f"task:{task.id}"]) from exc
    warnings = []
    freshness = pack.get("freshness") or {}
    if freshness.get("isStale") or freshness.get("warning"):
        warnings.append(_agent_warning("stale_task", "warning", freshness.get("warning") or "Task handoff may be stale.", [f"task:{task.id}"]))
    _audit_agent_tool_call(
        session,
        tool_name="get_handoff_pack",
        caller=caller,
        task_session_id=task.id,
        refs=_handoff_refs(pack),
        to_ref=f"task:{task.id}",
        budget=budget,
        warnings=warnings,
    )
    session.commit()
    return AgentHandoffResponse(
        taskSessionId=task.id,
        format=format,
        content=content,
        pack=pack,
        budget=budget,
        warnings=warnings,
        createdAt=utc_now(),
    )


@router.post("/proposals", response_model=MemoryProposalResponse)
def propose_agent_memory_api(
    payload: AgentMemoryProposalCreate,
    session: Session = Depends(get_session),
) -> MemoryProposalResponse:
    _validate_scope(session, task_session_id=payload.task_session_id, scope=payload.scope)
    try:
        proposal = create_memory_proposal(
            session,
            proposal_type=payload.type,
            title=payload.title,
            body=payload.body,
            target_store=payload.target_store,
            structured_payload=payload.structured_payload,
            scope=payload.scope,
            confidence=payload.confidence,
            review_note=payload.review_note,
            evidence_refs=payload.evidence_refs,
            task_session_id=payload.task_session_id,
        )
    except ValueError as exc:
        raise _agent_http_error(400, "invalid_request", str(exc)) from exc
    _audit_agent_tool_call(
        session,
        tool_name="propose_memory",
        caller=payload.caller,
        task_session_id=payload.task_session_id,
        scope=payload.scope,
        refs=proposal.evidence_refs or [],
        to_ref=f"proposal:{proposal.id}",
        write=True,
    )
    session.commit()
    session.refresh(proposal)
    return memory_proposal_to_response(proposal)


@router.get("/proposals", response_model=list[MemoryProposalResponse])
def list_agent_memory_proposals_api(
    caller: str = Query("agent"),
    status: str = "pending",
    session: Session = Depends(get_session),
) -> list[MemoryProposalResponse]:
    try:
        proposals = list_memory_proposals(session, status=status)
    except ValueError as exc:
        raise _agent_http_error(400, "invalid_request", str(exc)) from exc
    _audit_agent_tool_call(
        session,
        tool_name="list_memory_proposals",
        caller=caller,
        refs=[f"proposal:{proposal.id}" for proposal in proposals],
    )
    session.commit()
    return [memory_proposal_to_response(proposal) for proposal in proposals]


def _source_item_from_ref(session: Session, ref_value: str) -> SourceItem:
    try:
        ref = MemoryRef.parse(ref_value)
    except ValueError as exc:
        raise _agent_http_error(400, "invalid_ref", str(exc), refs=[ref_value]) from exc
    if ref.kind != "source":
        raise _agent_http_error(400, "invalid_ref", "get_source_excerpt only accepts source refs.", refs=[ref_value])
    source_item = session.get(SourceItem, ref.id)
    if not source_item or source_item.status != "active":
        raise _agent_http_error(404, "missing_ref", "Source ref was not found or is not active.", refs=[ref_value])
    return source_item


def _ensure_source_visible(
    source_item: SourceItem,
    *,
    task_session_id: str | None,
    scope: str | None,
    capabilities: list[str],
) -> None:
    metadata = source_item.metadata_json or {}
    source_task_id = metadata.get("taskSessionId")
    scoped_task_id = _task_id_from_scope(scope)
    requested_task_id = task_session_id or scoped_task_id
    if source_task_id and requested_task_id and source_task_id != requested_task_id:
        raise _agent_http_error(
            403,
            "permission_denied",
            "Source belongs to a different task scope.",
            refs=[f"source:{source_item.id}", f"task:{source_task_id}"],
        )
    source_scope_task_id = _task_id_from_scope(str(metadata.get("scope") or ""))
    if source_scope_task_id and requested_task_id and source_scope_task_id != requested_task_id:
        raise _agent_http_error(
            403,
            "permission_denied",
            "Source belongs to a different task scope.",
            refs=[f"source:{source_item.id}", f"task:{source_scope_task_id}"],
        )
    if (source_task_id or source_scope_task_id) and not requested_task_id:
        raise _agent_http_error(
            403,
            "permission_denied",
            "Task-scoped source requires taskSessionId.",
            refs=[f"source:{source_item.id}", f"task:{source_task_id or source_scope_task_id}"],
        )
    capability_set = set(capabilities)
    privacy_labels = metadata.get("privacyLabels") or []
    visibility = metadata.get("visibility") or "workspace"
    if visibility == "profile" and "profile_memory" not in capability_set:
        raise _agent_http_error(403, "permission_denied", "Profile source requires profile_memory capability.", refs=[f"source:{source_item.id}"])
    if visibility == "private" and not ({"private_memory", "sensitive_memory"} & capability_set):
        raise _agent_http_error(403, "permission_denied", "Private source requires private_memory capability.", refs=[f"source:{source_item.id}"])
    if privacy_labels and not ({"private_memory", "sensitive_memory", "profile_memory"} & capability_set):
        raise _agent_http_error(403, "permission_denied", "Sensitive source requires an explicit privacy capability.", refs=[f"source:{source_item.id}"])
    requirements = metadata.get("capabilityRequirements") or []
    required_capabilities = {str(item) for item in requirements if item}
    if not required_capabilities.issubset(capability_set):
        raise _agent_http_error(
            403,
            "permission_denied",
            "Source requires unavailable capability.",
            refs=[f"source:{source_item.id}"],
        )


def _validate_scope(session: Session, *, task_session_id: str | None, scope: str | None) -> None:
    if task_session_id and not get_task_session(session, task_session_id):
        raise _agent_http_error(404, "missing_ref", "Task session was not found.", refs=[f"task:{task_session_id}"])
    scoped_task_id = _task_id_from_scope(scope)
    if scoped_task_id and not get_task_session(session, scoped_task_id):
        raise _agent_http_error(404, "missing_ref", "Task session was not found.", refs=[f"task:{scoped_task_id}"])
    if task_session_id and scoped_task_id and task_session_id != scoped_task_id:
        raise _agent_http_error(
            403,
            "permission_denied",
            "taskSessionId and scope refer to different tasks.",
            refs=[f"task:{task_session_id}", f"task:{scoped_task_id}"],
        )


def _resolve_agent_capabilities(capability_profile: str | None, capabilities: list[str] | None) -> list[str]:
    try:
        return resolve_capabilities(capability_profile, capabilities)
    except ValueError as exc:
        raise _agent_http_error(400, "invalid_capability_profile", str(exc)) from exc


def _require_task(session: Session, task_id: str) -> TaskSession:
    task = get_task_session(session, task_id)
    if not task:
        raise _agent_http_error(404, "missing_ref", "Task session was not found.", refs=[f"task:{task_id}"])
    return task


def _ensure_task_mutable(task: TaskSession) -> None:
    try:
        ensure_task_mutable(task)
    except ValueError:
        raise _agent_http_error(409, "stale_task", "Terminal task cannot be mutated by agent tools.", refs=[f"task:{task.id}"])


def _task_id_from_scope(scope: str | None) -> str | None:
    if not scope:
        return None
    try:
        ref = MemoryRef.parse(scope)
    except ValueError:
        return None
    return ref.id if ref.kind == "task" else None


def _context_refs(pack: dict[str, Any]) -> list[str]:
    citation_refs = [str(ref.get("ref") or "") for ref in pack.get("citationRefs", [])]
    decision_refs = [str(ref.get("ref") or "") for ref in pack.get("decisionRefs", [])]
    return _dedupe_refs([*citation_refs, *decision_refs])


def _handoff_refs(pack: dict[str, Any]) -> list[str]:
    refs = [f"task:{pack.get('taskId')}"] if pack.get("taskId") else []
    refs.extend(str(item.get("ref") or "") for item in pack.get("checkpointRefs", []))
    refs.extend(str(item.get("ref") or "") for item in pack.get("sourceRefs", []))
    return _dedupe_refs(refs)


def _audit_agent_tool_call(
    session: Session,
    *,
    tool_name: str,
    caller: str,
    task_session_id: str | None = None,
    scope: str | None = None,
    refs: list[str] | None = None,
    to_ref: str | None = None,
    budget: dict | None = None,
    warnings: list[dict[str, Any]] | None = None,
    capability_profile: str | None = None,
    capabilities: list[str] | None = None,
    write: bool = False,
) -> None:
    clean_refs = _dedupe_refs(refs or [])
    record_provenance_event(
        session,
        event_type="agent_tool_write" if write else "agent_tool_read",
        from_ref=f"task:{task_session_id}" if task_session_id else None,
        to_ref=to_ref,
        reason=f"{(caller or 'agent').strip() or 'agent'} called {tool_name}",
        evidence_refs=clean_refs,
        payload={
            "tool": tool_name,
            "caller": (caller or "agent").strip() or "agent",
            "taskSessionId": task_session_id,
            "scope": scope,
            "budget": budget or {},
            "warnings": warnings or [],
            "refs": clean_refs,
            "capabilityProfile": capability_profile or "work",
            "capabilities": capabilities or [],
        },
        actor=(caller or "agent").strip() or "agent",
    )


def _dedupe_refs(refs: list[str]) -> list[str]:
    return [ref for ref in dict.fromkeys(refs) if ref]


def _agent_warning(code: str, severity: str, message: str, refs: list[str] | None = None) -> dict[str, Any]:
    return {"type": code, "severity": severity, "message": message, "refs": refs or []}


def _agent_http_error(status_code: int, code: str, message: str, refs: list[str] | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "refs": refs or []})
