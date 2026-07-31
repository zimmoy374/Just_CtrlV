import type { CaptureCard } from "../../types/cards"
import { API_BASE, parseResponse } from "./client"

export async function listActiveDays() {
  return parseResponse<string[]>(await fetch(`${API_BASE}/api/days`))
}

export async function listCards(dayKey: string) {
  return parseResponse<CaptureCard[]>(await fetch(`${API_BASE}/api/days/${encodeURIComponent(dayKey)}/cards`))
}

export async function createTextCard(input: { dayKey: string; textContent: string; x: number; y: number }) {
  return parseResponse<CaptureCard>(
    await fetch(`${API_BASE}/api/cards/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  )
}

export async function createLinkCard(input: { dayKey: string; url: string; x: number; y: number }) {
  return parseResponse<CaptureCard>(
    await fetch(`${API_BASE}/api/cards/link`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  )
}

export async function createImageCard(input: { dayKey: string; file: File; x: number; y: number }) {
  const form = new FormData()
  form.append("dayKey", input.dayKey)
  form.append("x", String(input.x))
  form.append("y", String(input.y))
  form.append("file", input.file)
  return parseResponse<CaptureCard>(
    await fetch(`${API_BASE}/api/cards/image`, {
      method: "POST",
      body: form,
    }),
  )
}

export async function patchCard(id: string, patch: Partial<CaptureCard>) {
  return parseResponse<CaptureCard>(
    await fetch(`${API_BASE}/api/cards/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  )
}

export async function retryAnalyze(id: string) {
  return parseResponse<CaptureCard>(await fetch(`${API_BASE}/api/cards/${id}/analyze`, { method: "POST" }))
}

export async function deleteCard(id: string) {
  return parseResponse<void>(await fetch(`${API_BASE}/api/cards/${id}`, { method: "DELETE" }))
}
