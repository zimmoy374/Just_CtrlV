import type { MemoryProposal } from "../../types/memory"
import { API_BASE, parseResponse } from "./client"

export async function listMemoryProposals(status = "pending") {
  const params = new URLSearchParams({ status })
  return parseResponse<MemoryProposal[]>(await fetch(`${API_BASE}/api/memory-proposals?${params}`))
}

export async function acceptMemoryProposal(id: string) {
  return parseResponse<MemoryProposal>(await fetch(`${API_BASE}/api/memory-proposals/${id}/accept`, { method: "POST" }))
}

export async function dismissMemoryProposal(id: string) {
  return parseResponse<MemoryProposal>(await fetch(`${API_BASE}/api/memory-proposals/${id}/dismiss`, { method: "POST" }))
}
