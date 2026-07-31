export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""

export async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const rawBody = await response.text()
    let message = response.statusText || "请求失败"
    try {
      const body = JSON.parse(rawBody) as { detail?: string }
      message = body.detail || message
    } catch {
      message = rawBody.trim() || message
    }
    if ([502, 503, 504].includes(response.status) || /bad gateway|econnrefused|proxy error/i.test(message)) {
      message = "后台服务未连接，正在等待恢复"
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



