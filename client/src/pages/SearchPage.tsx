import { useMemo } from "react"

import { SearchKnowledgeNetwork } from "../components/search-knowledge-network"
import type { KnowledgeSearchResult } from "../types/retrieval"
import { SearchResultsView } from "../components/search-results-view"
import { buildSearchKnowledgeNetwork } from "../lib/search-network"

type SearchPageProps = {
  query: string
  results: KnowledgeSearchResult[]
  isLoading: boolean
  onOpenCard: (result: KnowledgeSearchResult) => void
  onSearchKeyword: (keyword: string) => void
}

export function SearchPage({ query, results, isLoading, onOpenCard, onSearchKeyword }: SearchPageProps) {
  const network = useMemo(() => buildSearchKnowledgeNetwork(results, query), [query, results])

  return (
    <>
      {!isLoading ? <SearchKnowledgeNetwork network={network} onOpenResult={onOpenCard} onSearchKeyword={onSearchKeyword} /> : null}
      <SearchResultsView query={query} results={results} isLoading={isLoading} onOpenCard={onOpenCard} />
    </>
  )
}



