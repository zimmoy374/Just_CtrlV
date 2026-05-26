import type { ExportBundleResponse } from "../../types/export"
import { API_BASE, parseResponse } from "./client"

export async function exportKnowledgeBundle() {
  return parseResponse<ExportBundleResponse>(await fetch(`${API_BASE}/api/knowledge/export`, { method: "POST" }))
}



