import type { ExportBundleResponse } from "../../types/export"
import type { MemoryProposal } from "../../types/memory"
import type { ReviewProfileFact, ReviewProposalPatch, ReviewSource, ReviewConflict, ReviewWorkbench } from "../../types/review"
import { API_BASE, parseResponse } from "./client"

export async function getReviewWorkbench() {
  return parseResponse<ReviewWorkbench>(await fetch(`${API_BASE}/api/review/workbench?proposalStatus=all`))
}

export async function updateReviewProposal(id: string, payload: ReviewProposalPatch) {
  return parseResponse<MemoryProposal>(
    await fetch(`${API_BASE}/api/review/proposals/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  )
}

export async function acceptReviewProposal(id: string) {
  return parseResponse<MemoryProposal>(await fetch(`${API_BASE}/api/review/proposals/${id}/accept`, { method: "POST" }))
}

export async function dismissReviewProposal(id: string) {
  return parseResponse<MemoryProposal>(await fetch(`${API_BASE}/api/review/proposals/${id}/dismiss`, { method: "POST" }))
}

export async function supersedeProfileFact(id: string, payload: { objectValue: string; evidenceRefs: string[]; reviewNote?: string }) {
  return parseResponse<MemoryProposal>(
    await fetch(`${API_BASE}/api/review/profile-facts/${id}/supersede`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  )
}

export async function invalidateProfileFact(id: string, reason: string) {
  return parseResponse<ReviewProfileFact>(
    await fetch(`${API_BASE}/api/review/profile-facts/${id}/invalidate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }),
  )
}

export async function resolveReviewConflict(id: string, payload: { resolution: string; winningFactId?: string }) {
  return parseResponse<ReviewConflict>(
    await fetch(`${API_BASE}/api/review/conflicts/${id}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  )
}

export async function updateSourcePolicy(id: string, payload: { visibility: string; privacyLabels: string[] }) {
  return parseResponse<ReviewSource>(
    await fetch(`${API_BASE}/api/review/sources/${id}/policy`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  )
}

export async function purgeReviewSource(id: string, reason: string) {
  return parseResponse<ReviewSource>(
    await fetch(`${API_BASE}/api/review/sources/${id}/purge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }),
  )
}

export async function exportReviewBundle() {
  return parseResponse<ExportBundleResponse>(await fetch(`${API_BASE}/api/knowledge/export`, { method: "POST" }))
}

