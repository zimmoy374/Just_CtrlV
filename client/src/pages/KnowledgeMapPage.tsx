import type { CaptureCard } from "../types/cards"
import type { KnowledgeGraphResponse, KnowledgePageSummary } from "../types/knowledge"
import { KnowledgeGraphView } from "../components/knowledge-graph-view"

type KnowledgeMapPageProps = {
  graph: KnowledgeGraphResponse | null
  pages: KnowledgePageSummary[]
  isLoading: boolean
  onOpenCard: (card: CaptureCard) => void
  onSearchKeyword: (keyword: string) => void
}

export function KnowledgeMapPage({ graph, pages, isLoading, onOpenCard, onSearchKeyword }: KnowledgeMapPageProps) {
  return (
    <>
      <KnowledgeGraphView graph={graph} isLoading={isLoading} onOpenCard={onOpenCard} onSearchKeyword={onSearchKeyword} />
      {pages.length > 0 ? (
        <aside className="knowledge-pages-panel" aria-label="主题知识页">
          <div className="reflection-head">
            <span>{pages.length} 个主题页</span>
          </div>
          {pages.slice(0, 5).map((page) => (
            <article key={page.id}>
              <strong>{page.title}</strong>
              <p>{page.summary || "等待进一步编译"}</p>
              <div className="page-meta">
                <span>{page.status}</span>
                <span>{page.itemCount} 条知识</span>
              </div>
            </article>
          ))}
        </aside>
      ) : null}
    </>
  )
}



