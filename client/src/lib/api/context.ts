import type { ContextPack } from "../../types/context"
import { API_BASE, parseResponse } from "./client"

export async function getContextPack(query: string) {
  const params = new URLSearchParams({ q: query })
  return parseResponse<ContextPack>(await fetch(`${API_BASE}/api/knowledge/context?${params.toString()}`))
}



