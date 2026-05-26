import type { KnowledgeSearchResult } from "../../types/retrieval"
import { API_BASE, parseResponse } from "./client"

export async function searchKnowledge(query: string) {
  const params = new URLSearchParams({ q: query })
  return parseResponse<KnowledgeSearchResult[]>(await fetch(`${API_BASE}/api/knowledge/search?${params.toString()}`))
}



