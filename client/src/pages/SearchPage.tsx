import { useEffect, useMemo, useState } from "react"

import { SearchKnowledgeNetwork } from "../components/search-knowledge-network"
import type { KnowledgeSearchResult } from "../types/retrieval"
import { SearchResultsView } from "../components/search-results-view"
import { getContextPack } from "../lib/api/context"
import { buildSearchKnowledgeNetwork } from "../lib/search-network"
import type { ContextPack } from "../types/context"

type SearchPageProps = {
  query: string
  results: KnowledgeSearchResult[]
  isLoading: boolean
  onOpenCard: (result: KnowledgeSearchResult) => void
  onSearchKeyword: (keyword: string) => void
}

export function SearchPage({ query, results, isLoading, onOpenCard, onSearchKeyword }: SearchPageProps) {
  const network = useMemo(() => buildSearchKnowledgeNetwork(results, query), [query, results])
  const [contextPack, setContextPack] = useState<ContextPack | null>(null)
  const [isContextLoading, setIsContextLoading] = useState(false)

  useEffect(() => {
    const trimmed = query.trim()
    let cancelled = false
    const timer = window.setTimeout(() => {
      if (!trimmed) {
        setContextPack(null)
        setIsContextLoading(false)
        return
      }
      setIsContextLoading(true)
      void getContextPack(trimmed, { maxChars: 2400 })
        .then((pack) => {
          if (!cancelled) setContextPack(pack)
        })
        .catch(() => {
          if (!cancelled) setContextPack(null)
        })
        .finally(() => {
          if (!cancelled) setIsContextLoading(false)
        })
    }, 0)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [query])

  return (
    <>
      <ContextTraceSummary pack={contextPack} isLoading={isContextLoading} />
      {!isLoading ? <SearchKnowledgeNetwork network={network} onOpenResult={onOpenCard} onSearchKeyword={onSearchKeyword} /> : null}
      <SearchResultsView query={query} results={results} isLoading={isLoading} onOpenCard={onOpenCard} />
    </>
  )
}

function ContextTraceSummary({ pack, isLoading }: { pack: ContextPack | null; isLoading: boolean }) {
  const counts = useMemo(() => {
    const initial = { selected: 0, filtered: 0, deduped: 0, truncated: 0, skipped: 0 }
    for (const item of pack?.selectionTrace ?? []) {
      if (item.status in initial) {
        initial[item.status as keyof typeof initial] += 1
      }
    }
    return initial
  }, [pack])

  if (isLoading && !pack) {
    return (
      <section className="context-trace-strip" aria-label="ContextPack">
        <strong>ContextPack</strong>
        <span>计算中</span>
      </section>
    )
  }

  if (!pack) return null

  return (
    <section className="context-trace-strip" aria-label="ContextPack">
      <div>
        <strong>ContextPack</strong>
        <span>
          {pack.budget.usedChars}/{pack.budget.maxChars} chars{pack.budget.truncated ? " · truncated" : ""}
        </span>
      </div>
      <dl>
        <div>
          <dt>已选</dt>
          <dd>{counts.selected}</dd>
        </div>
        <div>
          <dt>过滤</dt>
          <dd>{counts.filtered}</dd>
        </div>
        <div>
          <dt>去重</dt>
          <dd>{counts.deduped}</dd>
        </div>
        <div>
          <dt>截断</dt>
          <dd>{counts.truncated + counts.skipped}</dd>
        </div>
      </dl>
    </section>
  )
}



