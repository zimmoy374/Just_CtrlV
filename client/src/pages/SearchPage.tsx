import type { KnowledgeSearchResult } from "../types/retrieval"
import { SearchResultsView } from "../components/search-results-view"

type SearchPageProps = {
  query: string
  results: KnowledgeSearchResult[]
  isLoading: boolean
  onOpenCard: (result: KnowledgeSearchResult) => void
}

export function SearchPage({ query, results, isLoading, onOpenCard }: SearchPageProps) {
  return <SearchResultsView query={query} results={results} isLoading={isLoading} onOpenCard={onOpenCard} />
}



