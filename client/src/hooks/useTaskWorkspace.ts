import { useCallback, useEffect, useState } from "react"

import { acceptMemoryProposal, dismissMemoryProposal, listMemoryProposals } from "../lib/api/memory-proposals"
import { archiveTask, closeTask, createTaskHandoff, getTask, getTaskHandoff, listTasks } from "../lib/api/tasks"
import type { MemoryProposal } from "../types/memory"
import type { HandoffPackResponse, TaskDetail, TaskSession } from "../types/tasks"

type WorkspaceNotifications = {
  setError: (value: string | null) => void
  setToast: (value: string | null) => void
}

export function useTaskWorkspace({ setError, setToast }: WorkspaceNotifications) {
  const [activeTasks, setActiveTasks] = useState<TaskSession[]>([])
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [taskDetail, setTaskDetail] = useState<TaskDetail | null>(null)
  const [handoff, setHandoff] = useState<HandoffPackResponse | null>(null)
  const [memoryProposals, setMemoryProposals] = useState<MemoryProposal[]>([])
  const [isTaskLoading, setIsTaskLoading] = useState(false)
  const [isInboxLoading, setIsInboxLoading] = useState(false)
  const [isHandoffCopying, setIsHandoffCopying] = useState(false)

  const refreshMemoryProposals = useCallback(async () => {
    setIsInboxLoading(true)
    try {
      setMemoryProposals(await listMemoryProposals("pending"))
    } catch (proposalError) {
      setError(proposalError instanceof Error ? proposalError.message : "记忆候选加载失败")
    } finally {
      setIsInboxLoading(false)
    }
  }, [setError])

  const refreshActiveTasks = useCallback(async () => {
    try {
      const tasks = await listTasks("active")
      setActiveTasks(tasks)
      setSelectedTaskId((current) => {
        if (current && tasks.some((task) => task.id === current)) return current
        return tasks[0]?.id ?? null
      })
    } catch (taskError) {
      setError(taskError instanceof Error ? taskError.message : "任务列表加载失败")
    }
  }, [setError])

  const refreshSelectedTask = useCallback(
    async (taskId: string | null) => {
      if (!taskId) {
        setTaskDetail(null)
        setHandoff(null)
        return
      }

      setIsTaskLoading(true)
      try {
        const [detail, handoffPreview] = await Promise.all([
          getTask(taskId),
          getTaskHandoff(taskId, { format: "markdown" }),
        ])
        setTaskDetail(detail)
        setHandoff(handoffPreview)
        setError(null)
      } catch (taskError) {
        setError(taskError instanceof Error ? taskError.message : "任务加载失败")
        setTaskDetail(null)
        setHandoff(null)
      } finally {
        setIsTaskLoading(false)
      }
    },
    [setError],
  )

  const copyHandoff = useCallback(async () => {
    if (!selectedTaskId) return
    if (!navigator.clipboard) {
      setError("当前环境不支持剪贴板")
      return
    }

    setIsHandoffCopying(true)
    try {
      const generated = await createTaskHandoff(selectedTaskId, { format: "markdown" })
      await navigator.clipboard.writeText(generated.content)
      setHandoff(generated)
      await refreshSelectedTask(selectedTaskId)
      setToast("Handoff 已复制")
    } catch (handoffError) {
      setError(handoffError instanceof Error ? handoffError.message : "复制 handoff 失败")
    } finally {
      setIsHandoffCopying(false)
    }
  }, [refreshSelectedTask, selectedTaskId, setError, setToast])

  const finishSelectedTask = useCallback(async () => {
    if (!selectedTaskId) return
    try {
      await closeTask(selectedTaskId)
      setToast("任务已完成，记忆候选已进入 inbox")
      await Promise.all([refreshActiveTasks(), refreshMemoryProposals()])
    } catch (taskError) {
      setError(taskError instanceof Error ? taskError.message : "完成任务失败")
    }
  }, [refreshActiveTasks, refreshMemoryProposals, selectedTaskId, setError, setToast])

  const archiveSelectedTask = useCallback(async () => {
    if (!selectedTaskId) return
    try {
      await archiveTask(selectedTaskId)
      setToast("任务已归档")
      await refreshActiveTasks()
    } catch (taskError) {
      setError(taskError instanceof Error ? taskError.message : "归档任务失败")
    }
  }, [refreshActiveTasks, selectedTaskId, setError, setToast])

  const acceptProposal = useCallback(
    async (id: string) => {
      try {
        await acceptMemoryProposal(id)
        setToast("记忆候选已接受")
        await refreshMemoryProposals()
      } catch (proposalError) {
        setError(proposalError instanceof Error ? proposalError.message : "接受记忆候选失败")
      }
    },
    [refreshMemoryProposals, setError, setToast],
  )

  const dismissProposal = useCallback(
    async (id: string) => {
      try {
        await dismissMemoryProposal(id)
        setToast("记忆候选已忽略")
        await refreshMemoryProposals()
      } catch (proposalError) {
        setError(proposalError instanceof Error ? proposalError.message : "忽略记忆候选失败")
      }
    },
    [refreshMemoryProposals, setError, setToast],
  )

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshActiveTasks()
      void refreshMemoryProposals()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [refreshActiveTasks, refreshMemoryProposals])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshSelectedTask(selectedTaskId)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [refreshSelectedTask, selectedTaskId])

  return {
    activeTasks,
    selectedTaskId,
    setSelectedTaskId,
    taskDetail,
    handoff,
    memoryProposals,
    isTaskLoading,
    isInboxLoading,
    isHandoffCopying,
    refreshActiveTasks,
    refreshMemoryProposals,
    copyHandoff,
    finishSelectedTask,
    archiveSelectedTask,
    acceptProposal,
    dismissProposal,
  }
}
