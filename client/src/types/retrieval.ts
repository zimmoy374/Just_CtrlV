import type { CaptureCard } from "./cards"

export type KnowledgeItem = {
  id: string
  sourceItemId: string
  cardId?: string | null
  title: string
  summary: string
  content: string
  keywords: string[]
  source: "second_brain" | "external_ai"
  sourceRef: string
  knowledgeType: "fragment" | "rule_preference" | "procedure_lesson"
  status: "active" | "merged" | "archived"
  createdAt: string
  updatedAt: string
}

export type KnowledgeSearchResult = {
  knowledgeItem: KnowledgeItem
  card?: CaptureCard | null
  matchedFields: string[]
  score: number
  excerpt?: string
  reason?: string
  source?: string
}


