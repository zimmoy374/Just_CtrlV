from __future__ import annotations

from typing import Any

from sqlmodel import Session

from ..models import SourceItem
from .context_helpers import PROTOCOL_REMINDER, char_count, excerpt_around, item_page_refs
from .protocol import MemoryQuery, MemorySlice
from .router import MemoryRouter, create_default_memory_router


class MemoryContextComposer:
    def __init__(self, router: MemoryRouter | None = None) -> None:
        self.router = router or create_default_memory_router()

    def retrieve_slices(self, session: Session, query: MemoryQuery) -> list[MemorySlice]:
        return self.router.retrieve(session, query)

    def build_context_pack(
        self,
        session: Session,
        *,
        query: str,
        task_session_id: str | None = None,
        scope: str | None = None,
        visibility: str = "workspace",
        capabilities: list[str] | tuple[str, ...] | None = None,
        max_pages: int = 3,
        max_items: int = 6,
        max_source_excerpts: int = 3,
        max_chars: int = 4000,
        max_task_slices: int = 4,
        max_rules: int = 4,
        max_profile_facts: int = 5,
        max_procedure_lessons: int = 3,
    ) -> dict[str, Any]:
        trimmed = query.strip()
        effective_scope = scope or (f"task:{task_session_id}" if task_session_id else None)
        retrieval_limit = max(max_items * 3, max_items + max_rules + max_procedure_lessons + max_pages * 2, 1)
        memory_query = MemoryQuery(
            text=trimmed,
            scope=effective_scope,
            task_session_id=task_session_id,
            limit=retrieval_limit,
            visibility=visibility,
            capabilities=tuple(capabilities or ()),
            max_chars=max_chars,
            max_pages=max_pages,
            max_items=max_items,
            max_source_excerpts=max_source_excerpts,
            max_task_slices=max_task_slices,
            max_rules=max_rules,
            max_profile_facts=max_profile_facts,
            max_procedure_lessons=max_procedure_lessons,
        )
        budget = {
            "maxPages": max_pages,
            "maxItems": max_items,
            "maxSourceExcerpts": max_source_excerpts,
            "maxChars": max_chars,
            "maxTaskSlices": max_task_slices,
            "maxRules": max_rules,
            "maxProfileFacts": max_profile_facts,
            "maxProcedureLessons": max_procedure_lessons,
            "usedChars": 0,
            "truncated": False,
        }
        pack: dict[str, Any] = {
            "query": trimmed,
            "protocolReminder": PROTOCOL_REMINDER,
            "taskState": None,
            "rules": [],
            "profileFacts": [],
            "procedureLessons": [],
            "relatedPages": [],
            "relatedItems": [],
            "sourceExcerpts": [],
            "warnings": [],
            "budget": budget,
            "citationRefs": [],
            "decisionRefs": [],
            "selectionTrace": [],
        }

        raw_slices = self.retrieve_slices(session, memory_query)
        visible_slices, filter_warnings, filter_trace = self._filter_slices(raw_slices, memory_query)
        deduped_slices, dedupe_trace = self._dedupe_slices(visible_slices)
        slices = self._rank_slices(deduped_slices, memory_query)
        selection_trace = [*filter_trace, *dedupe_trace]
        warnings = [*filter_warnings, *self._conflict_warnings(slices)]

        task_state_slices = [item for item in slices if item.kind == "task_state"]
        task_digest_slices = [item for item in slices if item.kind == "task_digest"]
        task_event_slices = [item for item in slices if item.kind == "task_event"]
        profile_slices = [item for item in slices if item.kind in {"profile_fact", "profile_relation"}]
        page_slices = [item for item in slices if item.kind == "knowledge_page"]
        knowledge_slices = [item for item in slices if item.kind == "knowledge_item"]
        rule_slices = [item for item in knowledge_slices if _knowledge_type(item) == "rule_preference"]
        procedure_slices = [item for item in knowledge_slices if _knowledge_type(item) == "procedure_lesson"]
        item_slices = [item for item in knowledge_slices if _knowledge_type(item) not in {"rule_preference", "procedure_lesson"}]

        citations: dict[str, dict[str, str]] = {}
        decisions: dict[str, dict[str, str]] = {}
        used_chars = 0

        if task_state_slices:
            digest_slice = task_digest_slices[0] if task_digest_slices else None
            event_limit = max(0, max_task_slices - 1 - (1 if digest_slice else 0))
            task_payload = self._task_state_payload(task_state_slices[0], task_event_slices[:event_limit], digest_slice)
            used_chars, added, payload_chars = _put_single_if_within_budget(pack, "taskState", task_payload, used_chars, max_chars)
            if added:
                selection_trace.append(_slice_trace(task_state_slices[0], "selected", section="taskState", reason="selected task state", used_chars=payload_chars))
                _collect_slice_refs(task_state_slices[0], citations, decisions)
                if digest_slice:
                    selection_trace.append(_slice_trace(digest_slice, "selected", section="taskState", reason="included task digest", used_chars=0))
                    _collect_slice_refs(digest_slice, citations, decisions)
                for event_slice in task_event_slices[:event_limit]:
                    selection_trace.append(_slice_trace(event_slice, "selected", section="taskState", reason="included recent task event", used_chars=0))
                    _collect_slice_refs(event_slice, citations, decisions)
                for event_slice in task_event_slices[event_limit:]:
                    selection_trace.append(_slice_trace(event_slice, "skipped", section="taskState", reason="skipped by maxTaskSlices", used_chars=0))
                if task_state_slices[0].staleness and task_state_slices[0].staleness != "fresh":
                    warnings.append(
                        {
                            "type": "stale_task",
                            "severity": "warning",
                            "message": f"任务上下文状态为 {task_state_slices[0].staleness}。",
                            "refs": [str(task_state_slices[0].ref)],
                        },
                    )
            else:
                budget["truncated"] = True
                selection_trace.append(_slice_trace(task_state_slices[0], "truncated", section="taskState", reason="skipped by maxChars", used_chars=0))

        for section in _section_order(trimmed):
            if section == "rules":
                used_chars = self._append_slice_section(
                    session,
                    pack,
                    "rules",
                    rule_slices,
                    max_rules,
                    used_chars,
                    max_chars,
                    citations,
                    decisions,
                    selection_trace,
                    "rule_preference",
                )
            elif section == "profileFacts":
                used_chars = self._append_profile_section(
                    pack,
                    profile_slices,
                    max_profile_facts,
                    used_chars,
                    max_chars,
                    citations,
                    decisions,
                    selection_trace,
                )
            elif section == "procedureLessons":
                used_chars = self._append_slice_section(
                    session,
                    pack,
                    "procedureLessons",
                    procedure_slices,
                    max_procedure_lessons,
                    used_chars,
                    max_chars,
                    citations,
                    decisions,
                    selection_trace,
                    "procedure_lesson",
                )
            elif section == "relatedPages":
                used_chars = self._append_page_section(pack, page_slices, max_pages, used_chars, max_chars, citations, decisions, selection_trace)
            elif section == "relatedItems":
                used_chars = self._append_slice_section(
                    session,
                    pack,
                    "relatedItems",
                    item_slices,
                    max_items,
                    used_chars,
                    max_chars,
                    citations,
                    decisions,
                    selection_trace,
                    "semantic_knowledge",
                )

        used_chars = self._append_source_excerpts(
            session,
            pack,
            self._rank_slices([*item_slices, *rule_slices, *procedure_slices], memory_query),
            trimmed,
            max_source_excerpts,
            used_chars,
            max_chars,
            citations,
            selection_trace,
        )

        if len(page_slices) > len(pack["relatedPages"]):
            budget["truncated"] = True
        if len(item_slices) > len(pack["relatedItems"]):
            budget["truncated"] = True
        if len(rule_slices) > len(pack["rules"]):
            budget["truncated"] = True
        if len(profile_slices) > len(pack["profileFacts"]):
            budget["truncated"] = True
        if len(procedure_slices) > len(pack["procedureLessons"]):
            budget["truncated"] = True

        budget["usedChars"] = used_chars
        pack["warnings"] = warnings
        pack["citationRefs"] = list(citations.values())
        pack["decisionRefs"] = list(decisions.values())
        pack["selectionTrace"] = selection_trace
        return pack

    def _filter_slices(self, slices: list[MemorySlice], query: MemoryQuery) -> tuple[list[MemorySlice], list[dict[str, Any]], list[dict[str, Any]]]:
        filtered: list[MemorySlice] = []
        warnings: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        counts = {"scope": 0, "privacy": 0, "capability": 0}

        for memory_slice in slices:
            if not _scope_allowed(memory_slice, query):
                counts["scope"] += 1
                continue
            if not _privacy_allowed(memory_slice, query):
                counts["privacy"] += 1
                continue
            if not _capabilities_allowed(memory_slice, query):
                counts["capability"] += 1
                continue
            filtered.append(memory_slice)

        if counts["scope"]:
            warnings.append(
                {
                    "type": "filtered_scope",
                    "severity": "info",
                    "message": f"{counts['scope']} 条记忆因范围不匹配被过滤。",
                    "refs": [],
                },
            )
            trace.append(_aggregate_trace("filtered", "scope", counts["scope"], "scope mismatch"))
        if counts["privacy"]:
            warnings.append(
                {
                    "type": "filtered_private",
                    "severity": "info",
                    "message": f"{counts['privacy']} 条私密记忆已被过滤。",
                    "refs": [],
                },
            )
            trace.append(_aggregate_trace("filtered", "privacy", counts["privacy"], "privacy or visibility boundary"))
        if counts["capability"]:
            warnings.append(
                {
                    "type": "insufficient_capability",
                    "severity": "info",
                    "message": f"{counts['capability']} 条记忆需要当前调用方没有声明的能力。",
                    "refs": [],
                },
            )
            trace.append(_aggregate_trace("filtered", "capability", counts["capability"], "missing declared capability"))
        return filtered, warnings, trace

    def _dedupe_slices(self, slices: list[MemorySlice]) -> tuple[list[MemorySlice], list[dict[str, Any]]]:
        deduped: list[MemorySlice] = []
        trace: list[dict[str, Any]] = []
        seen_refs: set[str] = set()
        seen_source_items: set[str] = set()
        for memory_slice in slices:
            ref = str(memory_slice.ref)
            if ref in seen_refs:
                trace.append(_slice_trace(memory_slice, "deduped", section=_trace_section(memory_slice), reason="duplicate ref", used_chars=0))
                continue
            source_item_id = str(memory_slice.metadata.get("sourceItemId") or "")
            if memory_slice.kind == "knowledge_item" and source_item_id:
                source_key = f"source:{source_item_id}"
                if source_key in seen_source_items:
                    trace.append(_slice_trace(memory_slice, "deduped", section=_trace_section(memory_slice), reason="duplicate source evidence", used_chars=0))
                    continue
                seen_source_items.add(source_key)
            seen_refs.add(ref)
            deduped.append(memory_slice)
        return deduped, trace

    def _rank_slices(self, slices: list[MemorySlice], query: MemoryQuery) -> list[MemorySlice]:
        requested_scope = query.scope or (f"task:{query.task_session_id}" if query.task_session_id else None)
        return sorted(slices, key=lambda memory_slice: (-_slice_utility(memory_slice, requested_scope), str(memory_slice.ref)))

    def _conflict_warnings(self, slices: list[MemorySlice]) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        for memory_slice in slices:
            if not memory_slice.conflict_refs:
                continue
            warnings.append(
                {
                    "type": "conflict",
                    "severity": "warning",
                    "message": "这条记忆存在尚未解决的冲突引用。",
                    "refs": [str(memory_slice.ref), *memory_slice.conflict_refs],
                },
            )
        return warnings

    def _task_state_payload(self, state_slice: MemorySlice, event_slices: list[MemorySlice], digest_slice: MemorySlice | None = None) -> dict[str, Any]:
        metadata = dict(state_slice.metadata)
        if digest_slice:
            metadata["taskDigest"] = {
                "ref": str(digest_slice.ref),
                "summary": digest_slice.summary,
                "excerpt": digest_slice.excerpt,
                "citationRef": digest_slice.citation_ref,
                "evidenceRefs": digest_slice.evidence_refs,
                "updatedAt": digest_slice.valid_at,
                "metadata": dict(digest_slice.metadata),
            }
        return {
            "ref": str(state_slice.ref),
            "title": state_slice.title,
            "summary": state_slice.summary,
            "excerpt": state_slice.excerpt,
            "scope": state_slice.scope,
            "staleness": state_slice.staleness,
            "citationRef": state_slice.citation_ref,
            "evidenceRefs": state_slice.evidence_refs,
            "decisionRef": state_slice.decision_ref,
            "updatedAt": state_slice.valid_at,
            "metadata": metadata,
            "recentEvents": [
                {
                    "ref": str(event_slice.ref),
                    "title": event_slice.title,
                    "summary": event_slice.summary,
                    "excerpt": event_slice.excerpt,
                    "eventType": str(event_slice.metadata.get("eventType") or ""),
                    "citationRef": event_slice.citation_ref,
                    "evidenceRefs": event_slice.evidence_refs,
                    "createdAt": event_slice.valid_at,
                }
                for event_slice in event_slices
            ],
        }

    def _append_page_section(
        self,
        pack: dict[str, Any],
        page_slices: list[MemorySlice],
        limit: int,
        used_chars: int,
        max_chars: int,
        citations: dict[str, dict[str, str]],
        decisions: dict[str, dict[str, str]],
        selection_trace: list[dict[str, Any]],
    ) -> int:
        for memory_slice in page_slices:
            if len(pack["relatedPages"]) >= limit:
                pack["budget"]["truncated"] = True
                selection_trace.append(_slice_trace(memory_slice, "skipped", section="relatedPages", reason="skipped by maxPages", used_chars=0))
                continue
            payload = {
                "id": memory_slice.ref.id,
                "title": memory_slice.title,
                "summary": memory_slice.summary,
                "status": str(memory_slice.metadata.get("status") or "active"),
                "keywords": _string_list(memory_slice.metadata.get("keywords")),
                "updatedAt": memory_slice.metadata.get("updatedAt"),
                "citationRef": memory_slice.citation_ref,
                "itemRefs": _string_list(memory_slice.metadata.get("itemRefs")),
                "evidenceRefs": memory_slice.evidence_refs,
                "decisionRef": memory_slice.decision_ref,
                "scope": memory_slice.scope,
            }
            used_chars, added, payload_chars = _append_if_within_budget(pack["relatedPages"], payload, used_chars, max_chars)
            if not added:
                pack["budget"]["truncated"] = True
                selection_trace.append(_slice_trace(memory_slice, "truncated", section="relatedPages", reason="skipped by maxChars", used_chars=0))
                continue
            selection_trace.append(_slice_trace(memory_slice, "selected", section="relatedPages", reason=memory_slice.reason or "selected knowledge page", used_chars=payload_chars))
            _collect_slice_refs(memory_slice, citations, decisions)
        return used_chars

    def _append_slice_section(
        self,
        session: Session,
        pack: dict[str, Any],
        section: str,
        slices: list[MemorySlice],
        limit: int,
        used_chars: int,
        max_chars: int,
        citations: dict[str, dict[str, str]],
        decisions: dict[str, dict[str, str]],
        selection_trace: list[dict[str, Any]],
        target_store: str,
    ) -> int:
        for memory_slice in slices:
            if len(pack[section]) >= limit:
                pack["budget"]["truncated"] = True
                selection_trace.append(_slice_trace(memory_slice, "skipped", section=section, reason=f"skipped by {section} limit", used_chars=0))
                continue
            payload = {
                "id": memory_slice.ref.id,
                "title": memory_slice.title,
                "summary": memory_slice.summary,
                "excerpt": memory_slice.excerpt,
                "score": memory_slice.score,
                "matchedFields": _string_list(memory_slice.metadata.get("matchedFields")),
                "reason": memory_slice.reason,
                "source": str(memory_slice.metadata.get("source") or ""),
                "sourceRef": str(memory_slice.metadata.get("sourceRef") or ""),
                "citationRef": memory_slice.citation_ref,
                "pageRefs": item_page_refs(session, memory_slice.ref.id),
                "updatedAt": memory_slice.metadata.get("updatedAt"),
                "evidenceRefs": memory_slice.evidence_refs,
                "decisionRef": memory_slice.decision_ref,
                "scope": memory_slice.scope,
                "knowledgeType": _knowledge_type(memory_slice),
                "targetStore": target_store,
            }
            used_chars, added, payload_chars = _append_if_within_budget(pack[section], payload, used_chars, max_chars)
            if not added:
                pack["budget"]["truncated"] = True
                selection_trace.append(_slice_trace(memory_slice, "truncated", section=section, reason="skipped by maxChars", used_chars=0))
                continue
            selection_trace.append(_slice_trace(memory_slice, "selected", section=section, reason=memory_slice.reason or f"selected for {section}", used_chars=payload_chars))
            _collect_slice_refs(memory_slice, citations, decisions)
        return used_chars

    def _append_profile_section(
        self,
        pack: dict[str, Any],
        profile_slices: list[MemorySlice],
        limit: int,
        used_chars: int,
        max_chars: int,
        citations: dict[str, dict[str, str]],
        decisions: dict[str, dict[str, str]],
        selection_trace: list[dict[str, Any]],
    ) -> int:
        for memory_slice in profile_slices:
            if len(pack["profileFacts"]) >= limit:
                pack["budget"]["truncated"] = True
                selection_trace.append(_slice_trace(memory_slice, "skipped", section="profileFacts", reason="skipped by maxProfileFacts", used_chars=0))
                continue
            payload = {
                "ref": str(memory_slice.ref),
                "kind": memory_slice.kind,
                "title": memory_slice.title,
                "summary": memory_slice.summary,
                "excerpt": memory_slice.excerpt,
                "score": memory_slice.score,
                "reason": memory_slice.reason,
                "scope": memory_slice.scope,
                "validAt": memory_slice.valid_at,
                "invalidAt": memory_slice.invalid_at,
                "evidenceRefs": memory_slice.evidence_refs,
                "citationRef": memory_slice.citation_ref,
                "decisionRef": memory_slice.decision_ref,
                "conflictRefs": memory_slice.conflict_refs,
                "metadata": dict(memory_slice.metadata),
            }
            used_chars, added, payload_chars = _append_if_within_budget(pack["profileFacts"], payload, used_chars, max_chars)
            if not added:
                pack["budget"]["truncated"] = True
                selection_trace.append(_slice_trace(memory_slice, "truncated", section="profileFacts", reason="skipped by maxChars", used_chars=0))
                continue
            selection_trace.append(_slice_trace(memory_slice, "selected", section="profileFacts", reason=memory_slice.reason or "selected profile fact", used_chars=payload_chars))
            _collect_slice_refs(memory_slice, citations, decisions)
        return used_chars

    def _append_source_excerpts(
        self,
        session: Session,
        pack: dict[str, Any],
        item_slices: list[MemorySlice],
        query: str,
        limit: int,
        used_chars: int,
        max_chars: int,
        citations: dict[str, dict[str, str]],
        selection_trace: list[dict[str, Any]],
    ) -> int:
        if not query:
            return used_chars
        seen_sources: set[str] = set()
        for memory_slice in item_slices:
            if len(pack["sourceExcerpts"]) >= limit:
                pack["budget"]["truncated"] = True
                selection_trace.append(_slice_trace(memory_slice, "skipped", section="sourceExcerpts", reason="skipped by maxSourceExcerpts", used_chars=0))
                continue
            source_item_id = str(memory_slice.metadata.get("sourceItemId") or "")
            if not source_item_id or source_item_id in seen_sources:
                if source_item_id in seen_sources:
                    selection_trace.append(_slice_trace(memory_slice, "deduped", section="sourceExcerpts", reason="duplicate source excerpt", used_chars=0))
                continue
            source_item = session.get(SourceItem, source_item_id)
            if not source_item or not source_item.content_text:
                selection_trace.append(_slice_trace(memory_slice, "skipped", section="sourceExcerpts", reason="missing source body", used_chars=0))
                continue
            excerpt = excerpt_around(source_item.content_text, query, limit=220)
            if not excerpt:
                selection_trace.append(_slice_trace(memory_slice, "skipped", section="sourceExcerpts", reason="no matching source excerpt", used_chars=0))
                continue
            source_ref = f"source:{source_item.id}"
            payload = {
                "id": source_ref,
                "sourceItemId": source_item.id,
                "knowledgeItemId": memory_slice.ref.id,
                "title": source_item.title,
                "kind": source_item.kind,
                "excerpt": excerpt,
                "citationRef": source_ref,
                "evidenceRefs": [source_ref],
            }
            used_chars, added, payload_chars = _append_if_within_budget(pack["sourceExcerpts"], payload, used_chars, max_chars)
            if not added:
                pack["budget"]["truncated"] = True
                selection_trace.append(_slice_trace(memory_slice, "truncated", section="sourceExcerpts", reason="skipped by maxChars", used_chars=0, ref=source_ref, citation_ref=source_ref))
                continue
            seen_sources.add(source_item_id)
            selection_trace.append(_slice_trace(memory_slice, "selected", section="sourceExcerpts", reason="selected source excerpt", used_chars=payload_chars, ref=source_ref, citation_ref=source_ref))
            citations[source_ref] = {
                "ref": source_ref,
                "kind": "source_excerpt",
                "id": source_item.id,
                "label": source_item.title,
            }
        return used_chars


def _scope_allowed(memory_slice: MemorySlice, query: MemoryQuery) -> bool:
    slice_scope = (memory_slice.scope or "workspace").strip() or "workspace"
    requested_scope = query.scope or (f"task:{query.task_session_id}" if query.task_session_id else None)
    if slice_scope == "workspace":
        return True
    if requested_scope and slice_scope == requested_scope:
        return True
    return False


def _privacy_allowed(memory_slice: MemorySlice, query: MemoryQuery) -> bool:
    capabilities = query.capability_set
    if memory_slice.visibility == "task":
        requested_scope = query.scope or (f"task:{query.task_session_id}" if query.task_session_id else None)
        if memory_slice.scope != requested_scope:
            return False
    if memory_slice.visibility == "private" and "private_memory" not in capabilities:
        return False
    if memory_slice.privacy_labels and not ({"private_memory", "sensitive_memory", "profile_memory"} & capabilities):
        return False
    return True


def _capabilities_allowed(memory_slice: MemorySlice, query: MemoryQuery) -> bool:
    requirements = set(_string_list(memory_slice.metadata.get("capabilityRequirements")))
    return requirements.issubset(query.capability_set)


def _knowledge_type(memory_slice: MemorySlice) -> str:
    return str(memory_slice.metadata.get("knowledgeType") or memory_slice.metadata.get("targetStore") or "fragment")


def _collect_slice_refs(
    memory_slice: MemorySlice,
    citations: dict[str, dict[str, str]],
    decisions: dict[str, dict[str, str]],
) -> None:
    if memory_slice.citation_ref:
        citations[memory_slice.citation_ref] = {
            "ref": memory_slice.citation_ref,
            "kind": memory_slice.kind,
            "id": memory_slice.ref.id,
            "label": memory_slice.title or memory_slice.summary or str(memory_slice.ref),
        }
    if memory_slice.decision_ref:
        decision_id = memory_slice.decision_ref.partition(":")[2] or memory_slice.decision_ref
        decisions[memory_slice.decision_ref] = {
            "ref": memory_slice.decision_ref,
            "kind": "memory_decision",
            "id": decision_id,
            "label": memory_slice.title or str(memory_slice.ref),
        }


def _append_if_within_budget(items: list[dict[str, Any]], payload: dict[str, Any], used_chars: int, max_chars: int) -> tuple[int, bool, int]:
    payload_chars = char_count(payload)
    if used_chars + payload_chars > max_chars:
        return used_chars, False, payload_chars
    items.append(payload)
    return used_chars + payload_chars, True, payload_chars


def _put_single_if_within_budget(
    pack: dict[str, Any],
    key: str,
    payload: dict[str, Any],
    used_chars: int,
    max_chars: int,
) -> tuple[int, bool, int]:
    payload_chars = char_count(payload)
    if used_chars + payload_chars > max_chars:
        return used_chars, False, payload_chars
    pack[key] = payload
    return used_chars + payload_chars, True, payload_chars


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _section_order(query: str) -> list[str]:
    intent = _query_intent(query)
    if intent == "procedure":
        return ["procedureLessons", "rules", "relatedItems", "relatedPages", "profileFacts"]
    if intent == "handoff":
        return ["procedureLessons", "rules", "relatedItems", "relatedPages", "profileFacts"]
    return ["rules", "profileFacts", "procedureLessons", "relatedPages", "relatedItems"]


def _query_intent(query: str) -> str:
    normalized = query.casefold()
    handoff_terms = ["handoff", "resume", "checkpoint", "接力", "继续", "交接", "下一步", "任务状态"]
    procedure_terms = ["procedure", "workflow", "lesson", "步骤", "流程", "经验", "踩坑", "怎么做"]
    rule_terms = ["rule", "preference", "policy", "规则", "偏好", "原则", "必须", "不要"]
    if any(term in normalized for term in handoff_terms):
        return "handoff"
    if any(term in normalized for term in procedure_terms):
        return "procedure"
    if any(term in normalized for term in rule_terms):
        return "rule"
    return "general"


def _slice_utility(memory_slice: MemorySlice, requested_scope: str | None) -> float:
    utility = float(memory_slice.score or 0.0)
    if memory_slice.citation_ref:
        utility += 8
    if memory_slice.evidence_refs:
        utility += 6
    if memory_slice.decision_ref:
        utility += 4
    if requested_scope and memory_slice.scope == requested_scope:
        utility += 6
    if memory_slice.scope == "workspace":
        utility += 1
    if memory_slice.kind == "task_state":
        utility += 12
    if memory_slice.kind in {"task_digest", "task_event"}:
        utility += 6
    return utility


def _aggregate_trace(status: str, category: str, count: int, reason: str) -> dict[str, Any]:
    return {
        "status": status,
        "ref": f"filtered:{category}",
        "kind": "filtered",
        "store": "memory_core",
        "section": "filter",
        "reason": f"{count} slice(s) {reason}",
        "score": 0.0,
        "usedChars": 0,
        "citationRef": "",
    }


def _slice_trace(
    memory_slice: MemorySlice,
    status: str,
    *,
    section: str,
    reason: str,
    used_chars: int,
    ref: str | None = None,
    citation_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "ref": ref or str(memory_slice.ref),
        "kind": memory_slice.kind,
        "store": memory_slice.store,
        "section": section,
        "reason": reason,
        "score": float(memory_slice.score or 0.0),
        "usedChars": used_chars,
        "citationRef": citation_ref if citation_ref is not None else (memory_slice.citation_ref or ""),
    }


def _trace_section(memory_slice: MemorySlice) -> str:
    if memory_slice.kind == "knowledge_page":
        return "relatedPages"
    if memory_slice.kind in {"profile_fact", "profile_relation"}:
        return "profileFacts"
    if memory_slice.kind in {"task_state", "task_digest", "task_event"}:
        return "taskState"
    if _knowledge_type(memory_slice) == "rule_preference":
        return "rules"
    if _knowledge_type(memory_slice) == "procedure_lesson":
        return "procedureLessons"
    return "relatedItems"
