import { useCallback, useEffect, useState } from "react"
import { ChevronLeft, ChevronRight, Home, Network, Search, Sparkles } from "lucide-react"

import { ImagePreviewOverlay } from "./components/image-preview-overlay"
import { SuggestionsPanel } from "./components/suggestions-panel"
import { Button } from "./components/ui/button"
import { WeekSummary } from "./components/week-summary"
import { useBoardController } from "./hooks/useBoardController"
import { useKnowledgeWorkspace } from "./hooks/useKnowledgeWorkspace"
import { BoardPage } from "./pages/BoardPage"
import { KnowledgeMapPage } from "./pages/KnowledgeMapPage"
import { SearchPage } from "./pages/SearchPage"
import type { KnowledgeSearchResult } from "./types/retrieval"

function App() {
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const knowledge = useKnowledgeWorkspace({ setError, setToast })
  const board = useBoardController({
    view: knowledge.view,
    setView: knowledge.setView,
    setError,
    setToast,
    refreshReflections: knowledge.refreshReflections,
  })

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 1800)
    return () => window.clearTimeout(timer)
  }, [toast])

  const handleOpenSearchResult = useCallback(
    (result: KnowledgeSearchResult) => {
      if (result.card) {
        board.openCardWeek(result.card)
      } else {
        setToast(`来源：${result.knowledgeItem.source}`)
      }
    },
    [board],
  )

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="week-controls" aria-label="周导航">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            title="上一周"
            onClick={() => board.setWeekStart(board.addWeeks(board.weekStart, -1))}
          >
            <ChevronLeft size={18} />
          </Button>
          <div className="week-label">
            <strong>{board.weekTitle}</strong>
            <span>{board.weekRange}</span>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            title="下一周"
            onClick={() => board.setWeekStart(board.addWeeks(board.weekStart, 1))}
          >
            <ChevronRight size={18} />
          </Button>
        </div>

        <form className="search-form" role="search" onSubmit={knowledge.handleSearchSubmit}>
          <Search size={17} />
          <input
            value={knowledge.searchInput}
            onChange={(event) => knowledge.setSearchInput(event.target.value)}
            placeholder="搜索知识"
            aria-label="搜索知识"
          />
          <button type="submit">搜索</button>
        </form>

        <div className="topbar-tools" aria-label="页面工具">
          <WeekSummary cards={board.cards} weekTitle={board.weekTitle} onSearchKeyword={(keyword) => void knowledge.runSearch(keyword)} />
          <button type="button" className="topbar-tool" title="待整理建议" onClick={() => void knowledge.refreshReflections()}>
            <Sparkles size={18} />
            {knowledge.reflections.length > 0 ? <span className="tool-count">{knowledge.reflections.length}</span> : null}
          </button>
          <button
            type="button"
            className={`topbar-tool${knowledge.view === "knowledge" ? " is-active" : ""}`}
            title="知识地图"
            onClick={() => void knowledge.openGraph()}
          >
            <Network size={18} />
          </button>
          <button type="button" className="topbar-tool" title="回到本周" onClick={board.goToday}>
            <Home size={18} />
          </button>
        </div>
      </header>

      <main className={`board-wrap view-${knowledge.view}`}>
        {knowledge.view === "board" ? (
          <BoardPage
            cards={board.cards}
            isLoading={board.isLoading}
            isPanning={board.isPanning}
            viewportRef={board.viewportRef}
            pan={board.pan}
            zoom={board.zoom}
            textComposer={board.textComposer}
            highlightedCardId={board.highlightedCardId}
            onTextComposerChange={board.setTextComposer}
            onComposerSubmit={board.handleComposerSubmit}
            onPointerDown={board.handlePointerDown}
            onPointerMove={board.handlePointerMove}
            onPointerUp={board.handlePointerUp}
            onDoubleClick={board.handleDoubleClick}
            onMove={board.handleMove}
            onDelete={board.handleDelete}
            onRetry={board.handleRetry}
            onCopyKeyword={board.handleCopyKeyword}
            onDeleteKeyword={board.handleDeleteKeyword}
            onOpenImage={board.openImagePreview}
          />
        ) : null}

        {knowledge.view === "search" ? (
          <SearchPage
            query={knowledge.searchQuery}
            results={knowledge.searchResults}
            isLoading={knowledge.isSearchLoading}
            onOpenCard={handleOpenSearchResult}
          />
        ) : null}

        {knowledge.view === "knowledge" ? (
          <KnowledgeMapPage
            graph={knowledge.graphData}
            pages={knowledge.knowledgePages}
            isLoading={knowledge.isGraphLoading}
            onOpenCard={board.openCardWeek}
            onSearchKeyword={(keyword) => void knowledge.runSearch(keyword)}
          />
        ) : null}

        {board.imagePreview ? (
          <ImagePreviewOverlay
            preview={board.imagePreview}
            onChange={board.setImagePreview}
            onClose={() => board.setImagePreview(null)}
          />
        ) : null}
        <SuggestionsPanel
          suggestions={knowledge.reflections}
          onAccept={knowledge.handleAcceptReflection}
          onDismiss={knowledge.handleDismissReflection}
        />
        {error ? <div className="error-banner">{error}</div> : null}
        {toast ? <div className="toast">{toast}</div> : null}
      </main>
    </div>
  )
}

export default App
