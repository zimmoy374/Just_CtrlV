from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from ..agent_runtime.capabilities import list_capability_profiles
from ..agent_runtime.protocol import (
    AgentProtocolError,
    agent_protocol_warning,
    audit_agent_tool_call,
    build_agent_context_pack,
    dedupe_refs,
    read_agent_source_excerpt,
    validate_agent_scope,
)
from ..database import get_session
from ..memory_kernel.proposals import create_memory_proposal, list_memory_proposals
from ..models import TaskSession, utc_now
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
    runtime_policy: dict[str, Any] = Field(alias="runtimePolicy")
    operating_rules: list[str] = Field(alias="operatingRules")
    workflow: list[dict[str, Any]]
    refs: dict[str, str]

    model_config = ConfigDict(populate_by_name=True)


def _agent_protocol_instructions() -> AgentProtocolInstructions:
    return AgentProtocolInstructions(
        name="second brain agent protocol",
        purpose="让外部工具安静地恢复和记录工作状态，按权限读取个人知识、引用原始证据，并把值得长期保存的内容提交为待审记忆。",
        toolsEndpoint="/api/agent/tools",
        runtimePolicy={
            "defaultMode": "balanced",
            "modes": {
                "quiet": "后台记录工作状态，不主动向用户提示成功记录。",
                "balanced": "默认模式。阶段性静默记录；只有保存、换 agent、明天继续、先到这等交接节点才短提示。",
                "verbose": "调试模式。可以向用户展示记录细节。",
            },
            "rules": [
                "不要在每次 record_progress 或 update_task_state 后告诉用户已经记录。",
                "用户表达保存、换 agent、明天继续、先到这时，创建 checkpoint 或 handoff，并只短提示一次。",
                "工作状态写入 task memory；长期价值内容只能提交 pending proposal。",
            ],
        },
        operatingRules=[
            "先读取 /api/agent/instructions，再读取 /api/agent/tools。",
            "读取个人资料、私密或敏感内容时，必须显式声明 capabilityProfile；默认 work 档位不会暴露这些内容。",
            "需要上下文时调用 /api/agent/context，不要尝试全量读取数据库或导出包。",
            "只在 ContextPack 返回 source: 引用后，才调用 /api/agent/source-excerpt 获取证据摘录。",
            "外部工具不能直接写入长期记忆，只能调用 /api/agent/proposals 提交待审记忆。",
            "外部工具不能接受、拒绝、覆盖、删除记忆，也不能解决冲突或清除原始证据。",
            "所有写入都必须带 caller；涉及具体任务时带 taskSessionId 或 task: scope。",
            "阶段性工作状态可以静默记录；用户不需要每次看到记录成功提示。",
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
        "record_task_event": ["只写工作状态事件，不写正式长期记忆；默认应静默记录，避免打扰用户。"],
        "update_task_state": ["只更新 task state，服务跨 agent 接力；不是长期记忆写入。"],
        "create_checkpoint": ["用于保存阶段快照；只在保存、换 agent、明天继续、先到这等节点短提示用户。"],
        "propose_memory": ["只能创建 pending 待审记忆；不暴露接受、解决冲突、失效事实或删除证据的能力。"],
        "get_context_pack": ["按预算和范围过滤；永远不返回全库内容。"],
        "get_source_excerpt": ["必须提供 source 引用；读取私密、个人资料或敏感证据需要显式能力。"],
        "get_handoff_pack": ["用于跨 agent 接力，不替代全量历史读取；过期或已关闭任务会明确提示。"],
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
    try:
        pack = build_agent_context_pack(
            session,
            q=q,
            caller=caller,
            task_session_id=task_session_id,
            scope=scope,
            capability_profile=capability_profile,
            capabilities=capabilities,
            item_limit=item_limit,
            page_limit=page_limit,
            source_excerpt_limit=source_excerpt_limit,
            profile_fact_limit=profile_fact_limit,
            max_chars=max_chars,
        )
    except AgentProtocolError as exc:
        raise _agent_protocol_http_error(exc) from exc
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
    try:
        payload = read_agent_source_excerpt(
            session,
            ref=ref,
            caller=caller,
            q=q,
            task_session_id=task_session_id,
            scope=scope,
            capability_profile=capability_profile,
            capabilities=capabilities,
            max_chars=max_chars,
        )
    except AgentProtocolError as exc:
        raise _agent_protocol_http_error(exc) from exc
    session.commit()
    return AgentSourceExcerptResponse.model_validate(payload)


@router.get("/tasks", response_model=list[TaskSessionResponse])
def list_agent_active_tasks_api(
    caller: str = Query("agent"),
    session: Session = Depends(get_session),
) -> list[TaskSessionResponse]:
    tasks = list_task_sessions(session, status="active")
    audit_agent_tool_call(
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
    audit_agent_tool_call(
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
    audit_agent_tool_call(
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
    audit_agent_tool_call(
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
        warnings.append(agent_protocol_warning("stale_task", "warning", freshness.get("warning") or "Task handoff may be stale.", [f"task:{task.id}"]))
    audit_agent_tool_call(
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
    try:
        validate_agent_scope(session, task_session_id=payload.task_session_id, scope=payload.scope)
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
    except AgentProtocolError as exc:
        raise _agent_protocol_http_error(exc) from exc
    except ValueError as exc:
        raise _agent_http_error(400, "invalid_request", str(exc)) from exc
    audit_agent_tool_call(
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
    audit_agent_tool_call(
        session,
        tool_name="list_memory_proposals",
        caller=caller,
        refs=[f"proposal:{proposal.id}" for proposal in proposals],
    )
    session.commit()
    return [memory_proposal_to_response(proposal) for proposal in proposals]


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


def _handoff_refs(pack: dict[str, Any]) -> list[str]:
    refs = [f"task:{pack.get('taskId')}"] if pack.get("taskId") else []
    refs.extend(str(item.get("ref") or "") for item in pack.get("checkpointRefs", []))
    refs.extend(str(item.get("ref") or "") for item in pack.get("sourceRefs", []))
    return dedupe_refs(refs)


def _agent_protocol_http_error(error: AgentProtocolError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


def _agent_http_error(status_code: int, code: str, message: str, refs: list[str] | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "refs": refs or []})
