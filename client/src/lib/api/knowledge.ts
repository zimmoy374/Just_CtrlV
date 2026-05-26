import type { ConfirmedKnowledgeImport, ConfirmedKnowledgeImportResponse, KnowledgeGraphResponse, KnowledgePageSummary } from "../../types/knowledge"
import { API_BASE, parseResponse } from "./client"

export async function getKnowledgeGraph() {
  return parseResponse<KnowledgeGraphResponse>(await fetch(`${API_BASE}/api/graph`))
}

export async function listKnowledgePages() {
  return parseResponse<KnowledgePageSummary[]>(await fetch(`${API_BASE}/api/knowledge/pages`))
}

export async function importConfirmedKnowledge(payload: ConfirmedKnowledgeImport) {
  return parseResponse<ConfirmedKnowledgeImportResponse>(
    await fetch(`${API_BASE}/api/knowledge/import-confirmed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  )
}


