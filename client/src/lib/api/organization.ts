import type { Reflection } from "../../types/organization"
import { API_BASE, parseResponse } from "./client"

export async function listReflections() {
  return parseResponse<Reflection[]>(await fetch(`${API_BASE}/api/reflections`))
}

export async function acceptReflection(id: string) {
  return parseResponse<Reflection>(await fetch(`${API_BASE}/api/reflections/${id}/accept`, { method: "POST" }))
}

export async function dismissReflection(id: string) {
  return parseResponse<Reflection>(await fetch(`${API_BASE}/api/reflections/${id}/dismiss`, { method: "POST" }))
}



