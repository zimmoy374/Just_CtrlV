import { CalendarDays, ExternalLink, ImageIcon, Search } from "lucide-react"

import { resolveAssetUrl } from "../lib/api"
import type { SearchResult } from "../types"

type SearchResultsViewProps = {
  query: string
  results: SearchResult[]
  isLoading: boolean
  onOpenCard: (result: SearchResult) => void
}

export function SearchResultsView({ query, results, isLoading, onOpenCard }: SearchResultsViewProps) {
  return (
    <section className="search-view" aria-label="搜索结果">
      <div className="view-heading">
        <div>
          <span className="view-kicker">Search Board</span>
          <h1>{query ? `“${query}”` : "搜索灵感"}</h1>
        </div>
        <strong>{isLoading ? "搜索中" : `${results.length} 条结果`}</strong>
      </div>

      {isLoading ? <div className="soft-empty">正在翻便签...</div> : null}

      {!isLoading && results.length === 0 ? (
        <div className="soft-empty">
          <Search size={30} />
          <span>没有匹配到关键词</span>
        </div>
      ) : null}

      <div className="result-grid">
        {results.map((result) => (
          <article className="result-card" key={result.card.id}>
            <button type="button" className="result-open" onClick={() => onOpenCard(result)} title="回到原周卡片">
              <ExternalLink size={15} />
            </button>
            <div className="result-meta">
              <CalendarDays size={14} />
              <span>{result.weekKey}</span>
              <em>{Math.round(result.score)}%</em>
            </div>
            {result.card.type === "image" ? (
              <div className="result-image">
                {result.card.imageUrl ? (
                  <img src={resolveAssetUrl(result.card.imageUrl)} alt={result.card.summary || "搜索到的灵感截图"} />
                ) : (
                  <ImageIcon size={28} />
                )}
              </div>
            ) : (
              <p className="result-text">{result.card.textContent}</p>
            )}
            {result.card.summary ? <p className="result-summary">{result.card.summary}</p> : null}
            <div className="result-keywords">
              {result.matchedKeywords.map((keyword) => (
                <span key={keyword}>{keyword}</span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
