from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlmodel import Session

from ..memory_core.composer import MemoryContextComposer
from ..memory_core.context_helpers import excerpt_around
from ..memory_core.decisions import record_provenance_event
from ..memory_core.protocol import MemoryRef
from ..models import SourceItem
from ..tasks.sessions import get_task_session
from .capabilities import resolve_capabilities


@dataclass(slots=True)
class AgentProtocolError(Exception):
    status_code: int
    code: str
    message: str
    refs: list[str]

    @property
    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "refs": self.refs}


def build_agent_context_pack(
    session: Session,
    *,
    q: str = "",
    caller: str = "agent",
    task_session_id: str | None = None,
    scope: str | None = None,
    capability_profile: str | None = None,
    capabilities: list[str] | None = None,
    item_limit: int = 6,
    page_limit: int = 3,
    source_excerpt_limit: int = 3,
    profile_fact_limit: int = 5,
    max_chars: int = 4000,
) -> dict[str, Any]:
    if max_chars < 500:
        raise agent_protocol_error(413, "budget_exceeded", "ContextPack 的 maxChars 至少为 500。")

    validate_agent_scope(session, task_session_id=task_session_id, scope=scope)
    resolved_capabilities = resolve_agent_protocol_capabilities(capability_profile, capabilities)
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
            agent_protocol_warning(
                "budget_exceeded",
                "warning",
                f"ContextPack 已为调用方 {caller} 截断；请缩小查询词或提高 maxChars。",
            ),
        )
    audit_agent_tool_call(
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
    return pack


def read_agent_source_excerpt(
    session: Session,
    *,
    ref: str,
    caller: str = "agent",
    q: str = "",
    task_session_id: str | None = None,
    scope: str | None = None,
    capability_profile: str | None = None,
    capabilities: list[str] | None = None,
    max_chars: int = 800,
) -> dict[str, Any]:
    if max_chars < 80:
        raise agent_protocol_error(413, "budget_exceeded", "证据摘录的 maxChars 至少为 80。", refs=[ref])

    validate_agent_scope(session, task_session_id=task_session_id, scope=scope)
    resolved_capabilities = resolve_agent_protocol_capabilities(capability_profile, capabilities)
    source_item = _source_item_from_ref(session, ref)
    _ensure_source_visible(source_item, task_session_id=task_session_id, scope=scope, capabilities=resolved_capabilities)

    excerpt = excerpt_around(source_item.content_text or "", q, limit=max_chars)
    truncated = len(" ".join((source_item.content_text or "").split())) > len(excerpt)
    warnings = [agent_protocol_warning("budget_exceeded", "warning", "证据摘录已按 maxChars 截断。")] if truncated else []
    source_ref = f"source:{source_item.id}"
    budget = {"maxChars": max_chars, "usedChars": len(excerpt), "truncated": truncated}
    audit_agent_tool_call(
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
    return {
        "ref": source_ref,
        "sourceItemId": source_item.id,
        "title": source_item.title,
        "kind": source_item.kind,
        "excerpt": excerpt,
        "citationRef": source_ref,
        "evidenceRefs": [source_ref],
        "budget": budget,
        "warnings": warnings,
    }


def validate_agent_scope(session: Session, *, task_session_id: str | None, scope: str | None) -> None:
    if task_session_id and not get_task_session(session, task_session_id):
        raise agent_protocol_error(404, "missing_ref", "Task session was not found.", refs=[f"task:{task_session_id}"])
    scoped_task_id = _task_id_from_scope(scope)
    if scoped_task_id and not get_task_session(session, scoped_task_id):
        raise agent_protocol_error(404, "missing_ref", "Task session was not found.", refs=[f"task:{scoped_task_id}"])
    if task_session_id and scoped_task_id and task_session_id != scoped_task_id:
        raise agent_protocol_error(
            403,
            "permission_denied",
            "taskSessionId and scope refer to different tasks.",
            refs=[f"task:{task_session_id}", f"task:{scoped_task_id}"],
        )


def resolve_agent_protocol_capabilities(capability_profile: str | None, capabilities: list[str] | None) -> list[str]:
    try:
        return resolve_capabilities(capability_profile, capabilities)
    except ValueError as exc:
        raise agent_protocol_error(400, "invalid_capability_profile", str(exc)) from exc


def audit_agent_tool_call(
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
    clean_refs = dedupe_refs(refs or [])
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


def dedupe_refs(refs: list[str]) -> list[str]:
    return [ref for ref in dict.fromkeys(refs) if ref]


def agent_protocol_warning(code: str, severity: str, message: str, refs: list[str] | None = None) -> dict[str, Any]:
    return {"type": code, "severity": severity, "message": message, "refs": refs or []}


def agent_protocol_error(status_code: int, code: str, message: str, refs: list[str] | None = None) -> AgentProtocolError:
    return AgentProtocolError(status_code=status_code, code=code, message=message, refs=refs or [])


def _source_item_from_ref(session: Session, ref_value: str) -> SourceItem:
    try:
        ref = MemoryRef.parse(ref_value)
    except ValueError as exc:
        raise agent_protocol_error(400, "invalid_ref", str(exc), refs=[ref_value]) from exc
    if ref.kind != "source":
        raise agent_protocol_error(400, "invalid_ref", "get_source_excerpt only accepts source refs.", refs=[ref_value])
    source_item = session.get(SourceItem, ref.id)
    if not source_item or source_item.status != "active":
        raise agent_protocol_error(404, "missing_ref", "Source ref was not found or is not active.", refs=[ref_value])
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
        raise agent_protocol_error(
            403,
            "permission_denied",
            "Source belongs to a different task scope.",
            refs=[f"source:{source_item.id}", f"task:{source_task_id}"],
        )
    source_scope_task_id = _task_id_from_scope(str(metadata.get("scope") or ""))
    if source_scope_task_id and requested_task_id and source_scope_task_id != requested_task_id:
        raise agent_protocol_error(
            403,
            "permission_denied",
            "Source belongs to a different task scope.",
            refs=[f"source:{source_item.id}", f"task:{source_scope_task_id}"],
        )
    if (source_task_id or source_scope_task_id) and not requested_task_id:
        raise agent_protocol_error(
            403,
            "permission_denied",
            "Task-scoped source requires taskSessionId.",
            refs=[f"source:{source_item.id}", f"task:{source_task_id or source_scope_task_id}"],
        )
    capability_set = set(capabilities)
    privacy_labels = metadata.get("privacyLabels") or []
    visibility = metadata.get("visibility") or "workspace"
    if visibility == "profile" and "profile_memory" not in capability_set:
        raise agent_protocol_error(403, "permission_denied", "Profile source requires profile_memory capability.", refs=[f"source:{source_item.id}"])
    if visibility == "private" and not ({"private_memory", "sensitive_memory"} & capability_set):
        raise agent_protocol_error(403, "permission_denied", "Private source requires private_memory capability.", refs=[f"source:{source_item.id}"])
    if privacy_labels and not ({"private_memory", "sensitive_memory", "profile_memory"} & capability_set):
        raise agent_protocol_error(403, "permission_denied", "Sensitive source requires an explicit privacy capability.", refs=[f"source:{source_item.id}"])
    requirements = metadata.get("capabilityRequirements") or []
    required_capabilities = {str(item) for item in requirements if item}
    if not required_capabilities.issubset(capability_set):
        raise agent_protocol_error(
            403,
            "permission_denied",
            "Source requires unavailable capability.",
            refs=[f"source:{source_item.id}"],
        )


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
    return dedupe_refs([*citation_refs, *decision_refs])
