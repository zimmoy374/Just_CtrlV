import type { CaptureCard } from "./cards"

export type KnowledgeItem = {
  id: string
  sourceItemId: string
  cardId?: string | null
  title: string
  summary: string
  content: string
  keywords: string[]
  source: string
  sourceRef: string
  knowledgeType: string
  status: string
  createdAt: string
  updatedAt: string
}

export type KnowledgeGraphNode = {
  id: string
  type: "keyword" | "item" | "page"
  label: string
  weekKey?: string | null
  count: number
  weeks: string[]
  card?: CaptureCard | null
  knowledgeItem?: KnowledgeItem | null
  status?: string | null
  itemCount: number
}

export type KnowledgeGraphEdge = {
  id: string
  source: string
  target: string
  keyword: string
}

export type KnowledgeGraphResponse = {
  nodes: KnowledgeGraphNode[]
  edges: KnowledgeGraphEdge[]
}

export type KnowledgePageSummary = {
  id: string
  title: string
  summary: string
  status: "draft" | "active" | "stale" | "archived"
  keywords: string[]
  updatedAt: string
  itemCount: number
}

export type ConfirmedKnowledgeImport = {
  title: string
  summary?: string
  body?: string
  keywords?: string[]
  selectedOriginalText: string
  sourceTitle?: string
  sourceUrl?: string
  externalId?: string
  proposedPages?: string[]
  metadata?: Record<string, unknown>
}

export type ConfirmedKnowledgeImportResponse = {
  sourceItemId: string
  knowledgeItem: KnowledgeItem
  suggestionIds: string[]
}


