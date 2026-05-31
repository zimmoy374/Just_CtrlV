import type { MemoryProposal, MemoryProposalType, MemoryTargetStore } from "./memory"

export type ReviewDecision = {
  ref: string
  decisionType: string
  targetRef: string
  actor: string
  reason: string
  policy: string
  evidenceRefs: string[]
  createdAt: string
}

export type ReviewProvenance = {
  ref: string
  type: string
  fromRef?: string | null
  toRef?: string | null
  actor: string
  reason: string
  evidenceRefs: string[]
  payload: Record<string, unknown>
  occurredAt: string
}

export type ReviewMemoryRecord = {
  ref: string
  id: string
  title: string
  summary: string
  status: string
  targetStore: string
  scope: string
  visibility: string
  privacyLabels: string[]
  evidenceRefs: string[]
  decisionRef?: string | null
  sourceRef?: string | null
  taskSessionId?: string | null
  updatedAt?: string | null
  decisionHistory: ReviewDecision[]
  provenanceHistory: ReviewProvenance[]
  metadata: Record<string, unknown>
}

export type ReviewProfileFact = {
  ref: string
  id: string
  title: string
  subject: string
  predicate: string
  objectValue: string
  status: string
  scope: string
  confidence?: number | null
  validAt: string
  invalidAt?: string | null
  supersededBy?: string | null
  evidenceRefs: string[]
  decisionRef?: string | null
  conflictRefs: string[]
  decisionHistory: ReviewDecision[]
  provenanceHistory: ReviewProvenance[]
}

export type ReviewConflict = {
  ref: string
  id: string
  type: string
  status: string
  reason: string
  resolution: string
  scope: string
  factRefs: string[]
  relationRefs: string[]
  decisionRef?: string | null
  createdAt: string
  resolvedAt?: string | null
  decisionHistory: ReviewDecision[]
  provenanceHistory: ReviewProvenance[]
}

export type ReviewSource = {
  ref: string
  id: string
  title: string
  kind: string
  source: string
  status: string
  visibility: string
  privacyLabels: string[]
  taskSessionId?: string | null
  contentChars: number
  excerpt: string
  updatedAt: string
  decisionHistory: ReviewDecision[]
  provenanceHistory: ReviewProvenance[]
}

export type ReviewWorkbench = {
  proposals: MemoryProposal[]
  profileFacts: ReviewProfileFact[]
  conflicts: ReviewConflict[]
  rules: ReviewMemoryRecord[]
  procedures: ReviewMemoryRecord[]
  pages: ReviewMemoryRecord[]
  sources: ReviewSource[]
  counts: Record<string, number>
}

export type ReviewProposalPatch = {
  type?: MemoryProposalType
  title?: string
  body?: string
  targetStore?: MemoryTargetStore
  structuredPayload?: Record<string, unknown>
  scope?: string
  evidenceRefs?: string[]
  confidence?: number
  reviewNote?: string
}
