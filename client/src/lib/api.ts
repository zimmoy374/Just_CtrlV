import type { InspirationCard } from "../types"

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      message = body.detail || message
    } catch {
      message = response.statusText
    }
    throw new Error(message)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export function resolveAssetUrl(path?: string | null) {
  if (!path) return ""
  if (!API_BASE || path.startsWith("http")) return path
  return `${API_BASE}${path}`
}

export async function listCards(weekKey: string) {
  return parseResponse<InspirationCard[]>(await fetch(`${API_BASE}/api/weeks/${weekKey}/cards`))
}

export async function createTextCard(input: { weekKey: string; textContent: string; x: number; y: number }) {
  return parseResponse<InspirationCard>(
    await fetch(`${API_BASE}/api/cards/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  )
}

export async function createImageCard(input: { weekKey: string; file: File; x: number; y: number }) {
  const form = new FormData()
  form.append("weekKey", input.weekKey)
  form.append("x", String(input.x))
  form.append("y", String(input.y))
  form.append("file", input.file)
  return parseResponse<InspirationCard>(
    await fetch(`${API_BASE}/api/cards/image`, {
      method: "POST",
      body: form,
    }),
  )
}

export async function patchCard(id: string, patch: Partial<InspirationCard>) {
  return parseResponse<InspirationCard>(
    await fetch(`${API_BASE}/api/cards/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  )
}

export async function retryAnalyze(id: string) {
  return parseResponse<InspirationCard>(await fetch(`${API_BASE}/api/cards/${id}/analyze`, { method: "POST" }))
}

export async function deleteCard(id: string) {
  return parseResponse<void>(await fetch(`${API_BASE}/api/cards/${id}`, { method: "DELETE" }))
}
