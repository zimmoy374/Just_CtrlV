import { useEffect, useState } from "react"

import { DailyDecorations } from "./components/daily-decorations"
import { DayCalendar } from "./components/day-calendar"
import { ImagePreviewOverlay } from "./components/image-preview-overlay"
import { PawMenu } from "./components/paw-menu"
import { useBoardController } from "./hooks/useBoardController"
import { BoardPage } from "./pages/BoardPage"

function App() {
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [isCalendarOpen, setIsCalendarOpen] = useState(false)
  const board = useBoardController({ setError, setToast })

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 1800)
    return () => window.clearTimeout(timer)
  }, [toast])

  return (
    <div className="app-shell">
      <DailyDecorations dayKey={board.selectedDay} />
      <time className="day-stamp" dateTime={board.selectedDay}>{formatDay(board.selectedDay)}</time>
      <PawMenu
        selectedDay={board.selectedDay}
        todayKey={board.todayKey}
        onOpenCalendar={() => setIsCalendarOpen(true)}
        onToday={() => board.setSelectedDay(board.todayKey)}
      />

      <main className="board-wrap">
        <BoardPage
          cards={board.cards}
          isLoading={board.isLoading}
          viewportRef={board.viewportRef}
          textComposer={board.textComposer}
          onTextComposerChange={board.setTextComposer}
          onComposerSubmit={board.handleComposerSubmit}
          onPointerMove={board.handleBoardPointerMove}
          onDoubleClick={board.handleDoubleClick}
          onMove={board.handleMove}
          onDelete={board.handleDelete}
          onRetry={board.handleRetry}
          onCopyKeyword={board.handleCopyKeyword}
          onDeleteKeyword={board.handleDeleteKeyword}
          onOpenImage={board.openImagePreview}
        />

        {board.imagePreview ? (
          <ImagePreviewOverlay
            preview={board.imagePreview}
            onChange={board.setImagePreview}
            onClose={() => board.setImagePreview(null)}
          />
        ) : null}
        {error ? <div className="error-banner">{error}</div> : null}
        {toast ? <div className="toast">{toast}</div> : null}
      </main>
      {isCalendarOpen ? (
        <DayCalendar
          selectedDay={board.selectedDay}
          todayKey={board.todayKey}
          availableDays={board.availableDays}
          onSelect={(dayKey) => {
            board.setSelectedDay(dayKey)
            setIsCalendarOpen(false)
          }}
          onClose={() => setIsCalendarOpen(false)}
        />
      ) : null}
    </div>
  )
}

export default App

function formatDay(dayKey: string) {
  const [year, month, day] = dayKey.split("-").map(Number)
  return new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "short" }).format(new Date(year, month - 1, day))
}
