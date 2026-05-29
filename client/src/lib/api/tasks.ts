import type { HandoffPackResponse, TaskDetail, TaskSession } from "../../types/tasks"
import { API_BASE, parseResponse } from "./client"

type HandoffOptions = {
  format?: "markdown" | "json"
  includeClosed?: boolean
}

function handoffParams({ format = "markdown", includeClosed = false }: HandoffOptions = {}) {
  const params = new URLSearchParams({ format })
  if (includeClosed) {
    params.set("includeClosed", "true")
  }
  return params
}

export async function listTasks(status = "active") {
  const params = new URLSearchParams({ status })
  return parseResponse<TaskSession[]>(await fetch(`${API_BASE}/api/tasks?${params}`))
}

export async function getTask(taskId: string) {
  return parseResponse<TaskDetail>(await fetch(`${API_BASE}/api/tasks/${taskId}`))
}

export async function getTaskHandoff(taskId: string, options?: HandoffOptions) {
  return parseResponse<HandoffPackResponse>(
    await fetch(`${API_BASE}/api/tasks/${taskId}/handoff?${handoffParams(options)}`),
  )
}

export async function createTaskHandoff(taskId: string, options?: HandoffOptions) {
  return parseResponse<HandoffPackResponse>(
    await fetch(`${API_BASE}/api/tasks/${taskId}/handoff?${handoffParams(options)}`, { method: "POST" }),
  )
}

export async function closeTask(taskId: string) {
  return parseResponse<TaskDetail>(await fetch(`${API_BASE}/api/tasks/${taskId}/close`, { method: "POST" }))
}

export async function archiveTask(taskId: string) {
  return parseResponse<TaskDetail>(await fetch(`${API_BASE}/api/tasks/${taskId}/archive`, { method: "POST" }))
}
