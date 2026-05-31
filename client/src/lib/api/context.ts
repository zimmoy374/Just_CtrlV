import type { ContextPack } from "../../types/context"
import { API_BASE, parseResponse } from "./client"

type ContextPackOptions = {
  taskSessionId?: string | null
  scope?: string | null
  capability?: string[]
}

export async function getContextPack(query: string, options: ContextPackOptions = {}) {
  const params = new URLSearchParams({ q: query })
  if (options.taskSessionId) params.set("taskSessionId", options.taskSessionId)
  if (options.scope) params.set("scope", options.scope)
  for (const capability of options.capability ?? []) {
    params.append("capability", capability)
  }
  return parseResponse<ContextPack>(await fetch(`${API_BASE}/api/knowledge/context?${params.toString()}`))
}



