import { useCallback, useEffect, useState } from "react"
import type { FormEvent } from "react"

import { getKnowledgeGraph, listKnowledgePages } from "../lib/api/knowledge"
import { acceptReflection, dismissReflection, listReflections } from "../lib/api/organization"
import { searchKnowledge } from "../lib/api/retrieval"
import type { KnowledgeGraphResponse, KnowledgePageSummary } from "../types/knowledge"
import type { Reflection } from "../types/organization"
import type { KnowledgeSearchResult } from "../types/retrieval"

export type AppView = "board" | "search" | "knowledge"

type WorkspaceNotifications = {
  setError: (value: string | null) => void
  setToast: (value: string | null) => void
}

export function useKnowledgeWorkspace({ setError, setToast }: WorkspaceNotifications) {
  const [view, setView] = useState<AppView>("board")
  const [searchInput, setSearchInput] = useState("")
  const [searchQuery, setSearchQuery] = useState("")
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResult[]>([])
  const [isSearchLoading, setIsSearchLoading] = useState(false)
  const [graphData, setGraphData] = useState<KnowledgeGraphResponse | null>(null)
  const [knowledgePages, setKnowledgePages] = useState<KnowledgePageSummary[]>([])
  const [isGraphLoading, setIsGraphLoading] = useState(false)
  const [reflections, setReflections] = useState<Reflection[]>([])

  const runSearch = useCallback(
    async (query: string) => {
      const trimmed = query.trim()
      if (!trimmed) {
        setToast("先输入一个关键词")
        return
      }

      setSearchInput(trimmed)
      setSearchQuery(trimmed)
      setView("search")
      setIsSearchLoading(true)
      try {
        setSearchResults(await searchKnowledge(trimmed))
        setError(null)
      } catch (searchError) {
        setError(searchError instanceof Error ? searchError.message : "搜索失败")
      } finally {
        setIsSearchLoading(false)
      }
    },
    [setError, setToast],
  )

  const refreshReflections = useCallback(async () => {
    try {
      setReflections(await listReflections())
    } catch {
      // Reflection hints are helpful but should not block the board.
    }
  }, [])

  const openGraph = useCallback(async () => {
    setView("knowledge")
    setIsGraphLoading(true)
    try {
      const [graph, pages] = await Promise.all([getKnowledgeGraph(), listKnowledgePages()])
      setGraphData(graph)
      setKnowledgePages(pages)
      setError(null)
    } catch (graphError) {
      setError(graphError instanceof Error ? graphError.message : "知识地图加载失败")
    } finally {
      setIsGraphLoading(false)
    }
  }, [setError])

  const handleSearchSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      void runSearch(searchInput)
    },
    [runSearch, searchInput],
  )

  const handleAcceptReflection = useCallback(
    async (id: string) => {
      try {
        await acceptReflection(id)
        setToast("已整理成主题")
        void refreshReflections()
      } catch (reflectionError) {
        setError(reflectionError instanceof Error ? reflectionError.message : "接受整理建议失败")
      }
    },
    [refreshReflections, setError, setToast],
  )

  const handleDismissReflection = useCallback(
    async (id: string) => {
      try {
        await dismissReflection(id)
        setToast("已忽略整理建议")
        void refreshReflections()
      } catch (reflectionError) {
        setError(reflectionError instanceof Error ? reflectionError.message : "忽略整理建议失败")
      }
    },
    [refreshReflections, setError, setToast],
  )

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshReflections()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [refreshReflections])

  return {
    view,
    setView,
    searchInput,
    setSearchInput,
    searchQuery,
    searchResults,
    isSearchLoading,
    graphData,
    knowledgePages,
    isGraphLoading,
    reflections,
    runSearch,
    refreshReflections,
    openGraph,
    handleSearchSubmit,
    handleAcceptReflection,
    handleDismissReflection,
  }
}
