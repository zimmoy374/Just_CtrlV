export type CardType = "image" | "text"
export type AiStatus = "pending" | "generating" | "done" | "failed"

export type InspirationCard = {
  id: string
  weekKey: string
  type: CardType
  textContent?: string | null
  imageUrl?: string | null
  summary?: string | null
  keywords: string[]
  x: number
  y: number
  width: number
  rotation: number
  styleSeed: string
  aiStatus: AiStatus
  aiError?: string | null
  createdAt: string
  updatedAt: string
}

export type SearchResult = {
  card: InspirationCard
  weekKey: string
  matchedKeywords: string[]
  score: number
}

export type KnowledgeGraphNode = {
  id: string
  type: "keyword" | "card"
  label: string
  weekKey?: string | null
  count: number
  weeks: string[]
  card?: InspirationCard | null
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
