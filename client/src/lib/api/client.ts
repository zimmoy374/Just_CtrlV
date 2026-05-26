export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""

export async function parseResponse<T>(response: Response): Promise<T> {
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



