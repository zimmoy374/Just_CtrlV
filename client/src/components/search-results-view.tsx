import { CalendarDays, ExternalLink, FileText, ImageIcon, Link, Search } from "lucide-react"

import { resolveAssetUrl } from "../lib/api/client"
import type { KnowledgeSearchResult } from "../types/retrieval"

type SearchResultsViewProps = {
  query: string
  results: KnowledgeSearchResult[]
  isLoading: boolean
  onOpenCard: (result: KnowledgeSearchResult) => void
}

export function SearchResultsView({ query, results, isLoading, onOpenCard }: SearchResultsViewProps) {
  return (
    <section className="search-view" aria-label="搜索结果">
      <div className="view-heading">
        <div>
          <span className="view-kicker">Search Board</span>
          <h1>{query ? `“${query}”` : "搜索知识"}</h1>
        </div>
        <strong>{isLoading ? "搜索中" : `${results.length} 条结果`}</strong>
      </div>

      {isLoading ? <div className="soft-empty">正在翻便签...</div> : null}

      {!isLoading && results.length === 0 ? (
        <div className="soft-empty">
          <Search size={30} />
          <span>没有匹配到知识</span>
        </div>
      ) : null}

      <div className="result-grid">
        {results.map((result) => (
          <article className="result-card" key={result.knowledgeItem.id}>
            {result.card ? (
              <button type="button" className="result-open" onClick={() => onOpenCard(result)} title="回到原周卡片">
                <ExternalLink size={15} />
              </button>
            ) : null}
            <div className="result-meta">
              <CalendarDays size={14} />
              <span>{result.card?.weekKey || "知识"}</span>
              <em>{Math.round(result.score)}%</em>
            </div>
            {result.card?.type === "image" ? (
              <div className="result-image">
                {result.card?.imageUrl ? (
                  <img src={resolveAssetUrl(result.card.imageUrl)} alt={result.card.summary || "搜索到的知识截图"} />
                ) : (
                  <ImageIcon size={28} />
                )}
              </div>
            ) : result.card?.type === "link" ? (
              <a className="result-link" href={result.card.sourceUrl || "#"} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                <span className="result-link-icon">
                  <Link size={18} />
                </span>
                <strong>{result.card.sourceTitle || result.card.sourceUrl || "链接"}</strong>
                {result.card.sourceDescription ? <span>{result.card.sourceDescription}</span> : null}
                <em>{result.card.sourceUrl || "打开链接"}</em>
              </a>
            ) : result.card?.type === "text" ? (
              <p className="result-text">{result.card.textContent}</p>
            ) : (
              <div className="result-knowledge">
                <FileText size={22} />
                <strong>{result.knowledgeItem.title || "长文知识"}</strong>
                <p>{result.knowledgeItem.summary || result.knowledgeItem.content}</p>
              </div>
            )}
            {result.knowledgeItem.summary ? <p className="result-summary">{result.knowledgeItem.summary}</p> : null}
            <div className="result-keywords">
              {result.matchedFields.map((field) => (
                <span key={field}>{field}</span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}


