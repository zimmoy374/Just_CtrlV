export type MemoryProposalStatus = "pending" | "accepted" | "dismissed"

export type MemoryTargetStore = "semantic_knowledge" | "profile_temporal_graph" | "rule_preference" | "procedure_lesson"

export type MemoryProposalType =
  | "lesson"
  | "pitfall"
  | "user_preference"
  | "project_rule"
  | "workflow_pattern"
  | "technical_decision"
  | "environment_fact"
  | "profile_fact"
  | "entity_relation"
  | "fact_supersession"
  | "page_update"

export type MemoryProposal = {
  id: string
  taskSessionId?: string | null
  targetStore: MemoryTargetStore
  type: MemoryProposalType
  title: string
  body: string
  structuredPayload: Record<string, unknown>
  scope: string
  evidenceRefs: string[]
  confidence?: number | null
  reviewNote: string
  status: MemoryProposalStatus
  sourceItemId?: string | null
  knowledgeItemId?: string | null
  pageId?: string | null
  decisionRef?: string | null
  createdAt: string
  resolvedAt?: string | null
}
