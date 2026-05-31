import type { CaptureCard } from "./cards"
import type { KnowledgeItem, KnowledgeSearchResult } from "./retrieval"

export type SearchNetworkNodeType = "query" | "keyword" | "item"

export type SearchNetworkNode = {
  id: string
  type: SearchNetworkNodeType
  label: string
  count: number
  weeks: string[]
  card?: CaptureCard | null
  knowledgeItem?: KnowledgeItem | null
  result?: KnowledgeSearchResult | null
  score?: number
}

export type SearchNetworkEdge = {
  id: string
  source: string
  target: string
  label: string
}

export type SearchKnowledgeNetwork = {
  query: string
  nodes: SearchNetworkNode[]
  edges: SearchNetworkEdge[]
}
