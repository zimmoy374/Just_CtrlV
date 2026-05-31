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


