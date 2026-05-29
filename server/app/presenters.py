from __future__ import annotations

from .models import Card, HandoffPack, KnowledgeItem, MemoryProposal, Reflection, TaskCheckpoint, TaskEvent, TaskSession, TaskState
from .schemas import (
    CardResponse,
    HandoffPackResponse,
    KnowledgeItemResponse,
    MemoryProposalResponse,
    ReflectionResponse,
    TaskCheckpointResponse,
    TaskDetailResponse,
    TaskEventResponse,
    TaskSessionResponse,
    TaskStateResponse,
)


def card_to_response(card: Card) -> CardResponse:
    return CardResponse(
        id=card.id,
        weekKey=card.week_key,
        type=card.type,
        textContent=card.text_content,
        imageUrl=f"/uploads/{card.image_filename}" if card.image_filename else None,
        sourceUrl=card.source_url,
        sourceTitle=card.source_title,
        sourceDescription=card.source_description,
        summary=card.summary,
        keywords=card.keywords or [],
        x=card.x,
        y=card.y,
        width=card.width,
        rotation=card.rotation,
        styleSeed=card.style_seed,
        aiStatus=card.ai_status,
        aiError=card.ai_error,
        createdAt=card.created_at,
        updatedAt=card.updated_at,
    )


def knowledge_item_to_response(knowledge_item: KnowledgeItem) -> KnowledgeItemResponse:
    return KnowledgeItemResponse(
        id=knowledge_item.id,
        sourceItemId=knowledge_item.source_item_id,
        cardId=knowledge_item.card_id,
        title=knowledge_item.title,
        summary=knowledge_item.summary,
        content=knowledge_item.content,
        keywords=knowledge_item.keywords or [],
        source=knowledge_item.source,
        sourceRef=knowledge_item.source_ref,
        knowledgeType=knowledge_item.knowledge_type,
        status=knowledge_item.status,
        createdAt=knowledge_item.created_at,
        updatedAt=knowledge_item.updated_at,
    )


def reflection_to_response(reflection: Reflection) -> ReflectionResponse:
    return ReflectionResponse(
        id=reflection.id,
        triggerKey=reflection.trigger_key,
        title=reflection.title,
        reason=reflection.reason,
        question=reflection.question,
        relatedKnowledgeItemIds=reflection.related_knowledge_item_ids or [],
        status=reflection.status,
        createdAt=reflection.created_at,
        resolvedAt=reflection.resolved_at,
    )


def memory_proposal_to_response(proposal: MemoryProposal) -> MemoryProposalResponse:
    return MemoryProposalResponse(
        id=proposal.id,
        taskSessionId=proposal.task_session_id,
        targetStore=proposal.target_store,
        type=proposal.type,
        title=proposal.title,
        body=proposal.body,
        structuredPayload=proposal.structured_payload_json or {},
        scope=proposal.scope,
        evidenceRefs=proposal.evidence_refs or [],
        confidence=proposal.confidence,
        reviewNote=proposal.review_note,
        status=proposal.status,
        sourceItemId=proposal.source_item_id,
        knowledgeItemId=proposal.knowledge_item_id,
        pageId=proposal.page_id,
        decisionRef=proposal.decision_ref,
        createdAt=proposal.created_at,
        resolvedAt=proposal.resolved_at,
    )


def task_session_to_response(task: TaskSession) -> TaskSessionResponse:
    return TaskSessionResponse(
        id=task.id,
        title=task.title,
        userGoal=task.user_goal,
        status=task.status,
        activeAgent=task.active_agent,
        createdAt=task.created_at,
        updatedAt=task.updated_at,
        lastEventAt=task.last_event_at,
        closedAt=task.closed_at,
        expiresAt=task.expires_at,
    )


def task_event_to_response(event: TaskEvent) -> TaskEventResponse:
    return TaskEventResponse(
        id=event.id,
        taskSessionId=event.task_session_id,
        type=event.type,
        summary=event.summary,
        payload=event.payload_json or {},
        source=event.source,
        sourceRef=event.source_ref,
        createdAt=event.created_at,
    )


def task_state_to_response(state: TaskState) -> TaskStateResponse:
    return TaskStateResponse(
        taskSessionId=state.task_session_id,
        currentGoal=state.current_goal,
        done=state.done_json or [],
        inProgress=state.in_progress_json or [],
        nextSteps=state.next_steps_json or [],
        openQuestions=state.open_questions_json or [],
        constraints=state.constraints_json or [],
        risks=state.risks_json or [],
        decisions=state.decisions_json or [],
        filesTouched=state.files_touched_json or [],
        confidence=state.confidence,
        updatedAt=state.updated_at,
    )


def task_checkpoint_to_response(checkpoint: TaskCheckpoint) -> TaskCheckpointResponse:
    return TaskCheckpointResponse(
        id=checkpoint.id,
        taskSessionId=checkpoint.task_session_id,
        title=checkpoint.title,
        summary=checkpoint.summary,
        stateSnapshot=checkpoint.state_snapshot_json or {},
        eventFromId=checkpoint.event_from_id,
        eventToId=checkpoint.event_to_id,
        createdAt=checkpoint.created_at,
    )


def task_detail_to_response(
    task: TaskSession,
    state: TaskState,
    events: list[TaskEvent],
    checkpoints: list[TaskCheckpoint],
) -> TaskDetailResponse:
    return TaskDetailResponse(
        task=task_session_to_response(task),
        state=task_state_to_response(state),
        events=[task_event_to_response(event) for event in events],
        checkpoints=[task_checkpoint_to_response(checkpoint) for checkpoint in checkpoints],
    )


def handoff_pack_to_response(handoff: HandoffPack, pack: dict) -> HandoffPackResponse:
    return HandoffPackResponse(
        id=handoff.id,
        taskSessionId=handoff.task_session_id,
        format=handoff.format,
        content=handoff.content,
        pack=pack,
        budget=handoff.budget_json or {},
        createdAt=handoff.created_at,
    )
