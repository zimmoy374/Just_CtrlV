export type ContextCitationRef = {
  ref: string
  kind: string
  id: string
  label: string
}

export type ContextKnowledgeEntry = {
  id: string
  title: string
  summary: string
  excerpt: string
  score: number
  matchedFields: string[]
  reason: string
  source: string
  sourceRef: string
  citationRef: string
  pageRefs: string[]
  updatedAt?: string | null
  evidenceRefs: string[]
  decisionRef?: string | null
  scope?: string | null
  knowledgeType: string
  targetStore: string
}

export type ContextPageEntry = {
  id: string
  title: string
  summary: string
  status: string
  keywords: string[]
  updatedAt?: string | null
  citationRef: string
  itemRefs: string[]
  evidenceRefs: string[]
  decisionRef?: string | null
  scope?: string | null
}

export type ContextSourceExcerpt = {
  id: string
  sourceItemId: string
  knowledgeItemId: string
  title: string
  kind: string
  excerpt: string
  citationRef: string
  evidenceRefs: string[]
}

export type ContextTaskEvent = {
  ref: string
  title: string
  summary: string
  excerpt: string
  eventType: string
  citationRef: string
  evidenceRefs: string[]
  createdAt?: string | null
}

export type ContextTaskState = {
  ref: string
  title: string
  summary: string
  excerpt: string
  scope?: string | null
  staleness?: string | null
  citationRef: string
  evidenceRefs: string[]
  decisionRef?: string | null
  updatedAt?: string | null
  metadata: Record<string, unknown>
  recentEvents: ContextTaskEvent[]
}

export type ContextProfileFact = {
  ref: string
  kind: string
  title: string
  summary: string
  excerpt: string
  score: number
  reason: string
  scope?: string | null
  validAt?: string | null
  invalidAt?: string | null
  evidenceRefs: string[]
  citationRef: string
  decisionRef?: string | null
  conflictRefs: string[]
  metadata: Record<string, unknown>
}

export type ContextWarning = {
  type: string
  severity: string
  message: string
  refs: string[]
}

export type ContextSelectionTraceEntry = {
  status: string
  ref: string
  kind: string
  store: string
  section: string
  reason: string
  score: number
  usedChars: number
  citationRef: string
}

export type ContextPack = {
  query: string
  protocolReminder: string[]
  taskState?: ContextTaskState | null
  rules: ContextKnowledgeEntry[]
  profileFacts: ContextProfileFact[]
  procedureLessons: ContextKnowledgeEntry[]
  relatedPages: ContextPageEntry[]
  relatedItems: ContextKnowledgeEntry[]
  sourceExcerpts: ContextSourceExcerpt[]
  warnings: ContextWarning[]
  budget: {
    maxPages: number
    maxItems: number
    maxSourceExcerpts: number
    maxChars: number
    maxTaskSlices: number
    maxRules: number
    maxProfileFacts: number
    maxProcedureLessons: number
    usedChars: number
    truncated: boolean
  }
  citationRefs: ContextCitationRef[]
  decisionRefs: ContextCitationRef[]
  selectionTrace: ContextSelectionTraceEntry[]
}
