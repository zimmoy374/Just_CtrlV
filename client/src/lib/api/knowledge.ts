import type { ConfirmedKnowledgeImport, ConfirmedKnowledgeImportResponse } from "../../types/knowledge"
import { API_BASE, parseResponse } from "./client"

export async function importConfirmedKnowledge(payload: ConfirmedKnowledgeImport) {
  return parseResponse<ConfirmedKnowledgeImportResponse>(
    await fetch(`${API_BASE}/api/knowledge/import-confirmed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  )
}


