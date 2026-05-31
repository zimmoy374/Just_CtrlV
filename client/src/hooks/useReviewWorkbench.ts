import { useCallback, useState } from "react"

import {
  acceptReviewProposal,
  dismissReviewProposal,
  exportReviewBundle,
  getReviewWorkbench,
  invalidateProfileFact,
  purgeReviewSource,
  resolveReviewConflict,
  supersedeProfileFact,
  updateReviewProposal,
  updateSourcePolicy,
} from "../lib/api/review"
import type { ReviewProposalPatch, ReviewWorkbench } from "../types/review"

type WorkspaceNotifications = {
  setError: (value: string | null) => void
  setToast: (value: string | null) => void
}

export function useReviewWorkbench({ setError, setToast }: WorkspaceNotifications) {
  const [workbench, setWorkbench] = useState<ReviewWorkbench | null>(null)
  const [isReviewLoading, setIsReviewLoading] = useState(false)
  const [exportPath, setExportPath] = useState("")

  const refreshWorkbench = useCallback(async () => {
    setIsReviewLoading(true)
    try {
      setWorkbench(await getReviewWorkbench())
      setError(null)
    } catch (reviewError) {
      setError(reviewError instanceof Error ? reviewError.message : "记忆审查台加载失败")
    } finally {
      setIsReviewLoading(false)
    }
  }, [setError])

  const saveProposal = useCallback(
    async (id: string, payload: ReviewProposalPatch) => {
      try {
        await updateReviewProposal(id, payload)
        setToast("待审记忆已更新")
        await refreshWorkbench()
      } catch (reviewError) {
        setError(reviewError instanceof Error ? reviewError.message : "待审记忆更新失败")
      }
    },
    [refreshWorkbench, setError, setToast],
  )

  const acceptProposal = useCallback(
    async (id: string) => {
      try {
        await acceptReviewProposal(id)
        setToast("待审记忆已接受")
        await refreshWorkbench()
      } catch (reviewError) {
        setError(reviewError instanceof Error ? reviewError.message : "待审记忆接受失败")
      }
    },
    [refreshWorkbench, setError, setToast],
  )

  const dismissProposal = useCallback(
    async (id: string) => {
      try {
        await dismissReviewProposal(id)
        setToast("待审记忆已拒绝")
        await refreshWorkbench()
      } catch (reviewError) {
        setError(reviewError instanceof Error ? reviewError.message : "待审记忆拒绝失败")
      }
    },
    [refreshWorkbench, setError, setToast],
  )

  const supersedeFact = useCallback(
    async (id: string, objectValue: string, evidenceRefs: string[], reviewNote: string) => {
      try {
        await supersedeProfileFact(id, { objectValue, evidenceRefs, reviewNote })
        setToast("事实替代已进入审查")
        await refreshWorkbench()
      } catch (reviewError) {
        setError(reviewError instanceof Error ? reviewError.message : "事实替代失败")
      }
    },
    [refreshWorkbench, setError, setToast],
  )

  const invalidateFact = useCallback(
    async (id: string, reason: string) => {
      try {
        await invalidateProfileFact(id, reason)
        setToast("个人事实已失效")
        await refreshWorkbench()
      } catch (reviewError) {
        setError(reviewError instanceof Error ? reviewError.message : "事实失效失败")
      }
    },
    [refreshWorkbench, setError, setToast],
  )

  const resolveConflict = useCallback(
    async (id: string, resolution: string, winningFactId?: string) => {
      try {
        await resolveReviewConflict(id, { resolution, winningFactId })
        setToast("冲突已解决")
        await refreshWorkbench()
      } catch (reviewError) {
        setError(reviewError instanceof Error ? reviewError.message : "冲突解决失败")
      }
    },
    [refreshWorkbench, setError, setToast],
  )

  const saveSourcePolicy = useCallback(
    async (id: string, visibility: string, privacyLabels: string[]) => {
      try {
        await updateSourcePolicy(id, { visibility, privacyLabels })
        setToast("证据权限已更新")
        await refreshWorkbench()
      } catch (reviewError) {
        setError(reviewError instanceof Error ? reviewError.message : "证据权限更新失败")
      }
    },
    [refreshWorkbench, setError, setToast],
  )

  const purgeSource = useCallback(
    async (id: string, reason: string) => {
      try {
        await purgeReviewSource(id, reason)
        setToast("证据已清除")
        await refreshWorkbench()
      } catch (reviewError) {
        setError(reviewError instanceof Error ? reviewError.message : "证据清除失败")
      }
    },
    [refreshWorkbench, setError, setToast],
  )

  const exportBundle = useCallback(async () => {
    try {
      const exported = await exportReviewBundle()
      setExportPath(exported.exportPath)
      setToast("记忆包已导出")
    } catch (reviewError) {
      setError(reviewError instanceof Error ? reviewError.message : "导出失败")
    }
  }, [setError, setToast])

  return {
    workbench,
    isReviewLoading,
    exportPath,
    refreshWorkbench,
    saveProposal,
    acceptProposal,
    dismissProposal,
    supersedeFact,
    invalidateFact,
    resolveConflict,
    saveSourcePolicy,
    purgeSource,
    exportBundle,
  }
}
