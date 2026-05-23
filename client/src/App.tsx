import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { FormEvent, MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent } from "react"
import { CalendarDays, ChevronLeft, ChevronRight, Plus, RefreshCw, X } from "lucide-react"

import { createImageCard, createTextCard, deleteCard, listCards, patchCard, retryAnalyze } from "./lib/api"
import { addWeeks, formatWeekRange, getIsoWeekInfo, getIsoWeekStart, getWeekKey } from "./lib/dates"
import type { InspirationCard } from "./types"
import { BoardCard } from "./components/board-card"
import { ImagePreviewOverlay, type ImagePreviewState } from "./components/image-preview-overlay"
import { Button } from "./components/ui/button"
import { Textarea } from "./components/ui/textarea"

type Point = {
  x: number
  y: number
}

type TextComposer = Point & {
  text: string
}

type PanState = {
  pointerId: number
  startX: number
  startY: number
  originX: number
  originY: number
}

const BOARD_INTERACTIVE_SELECTOR = ".inspiration-card,.inline-composer,button,textarea,input"
const TEXT_ENTRY_SELECTOR = "textarea,input,[contenteditable='true']"

function App() {
  const [weekStart, setWeekStart] = useState(() => getIsoWeekStart(new Date()))
  const [cards, setCards] = useState<InspirationCard[]>([])
  const [textComposer, setTextComposer] = useState<TextComposer | null>(null)
  const [pan, setPan] = useState<Point>({ x: 0, y: 0 })
  const [isPanning, setIsPanning] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [imagePreview, setImagePreview] = useState<ImagePreviewState | null>(null)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const panRef = useRef<PanState | null>(null)
  const lastCanvasPointRef = useRef<Point | null>(null)

  const weekKey = useMemo(() => getWeekKey(weekStart), [weekStart])
  const weekInfo = useMemo(() => getIsoWeekInfo(weekStart), [weekStart])
  const weekRange = useMemo(() => formatWeekRange(weekStart), [weekStart])

  const loadWeek = useCallback(async () => {
    try {
      setIsLoading(true)
      setCards(await listCards(weekKey))
      setError(null)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载失败")
    } finally {
      setIsLoading(false)
    }
  }, [weekKey])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadWeek()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadWeek])

  useEffect(() => {
    if (!cards.some((card) => card.aiStatus === "pending" || card.aiStatus === "generating")) {
      return
    }
    const timer = window.setInterval(() => {
      void loadWeek()
    }, 2200)
    return () => window.clearInterval(timer)
  }, [cards, loadWeek])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 1800)
    return () => window.clearTimeout(timer)
  }, [toast])

  const clientToCanvasPoint = useCallback(
    (clientX: number, clientY: number): Point => {
      const rect = viewportRef.current?.getBoundingClientRect()
      return {
        x: Math.max(24, clientX - (rect?.left ?? 0) - pan.x),
        y: Math.max(24, clientY - (rect?.top ?? 0) - pan.y),
      }
    },
    [pan.x, pan.y],
  )

  const getDropPoint = useCallback(
    (preferred?: Point | null): Point => {
      if (preferred) return preferred
      const rect = viewportRef.current?.getBoundingClientRect()
      const offset = (cards.length % 8) * 26
      return {
        x: Math.max(48, (rect?.width ?? 1200) / 2 - pan.x - 160 + offset),
        y: Math.max(84, (rect?.height ?? 720) / 2 - pan.y - 130 + offset / 2),
      }
    },
    [cards.length, pan.x, pan.y],
  )

  const mergeCard = useCallback((updated: InspirationCard) => {
    setCards((current) => current.map((card) => (card.id === updated.id ? updated : card)))
  }, [])

  const handleCreateText = useCallback(
    async (text: string, point?: Point | null) => {
      const trimmed = text.trim()
      if (!trimmed) return
      const dropPoint = getDropPoint(point)
      try {
        const created = await createTextCard({ weekKey, textContent: trimmed, ...dropPoint })
        setCards((current) => [...current, created])
        setTextComposer(null)
        setError(null)
      } catch (createError) {
        setError(createError instanceof Error ? createError.message : "新增文本失败")
      }
    },
    [getDropPoint, weekKey],
  )

  const handleCreateImage = useCallback(
    async (file: File, point?: Point | null) => {
      const dropPoint = getDropPoint(point)
      try {
        const created = await createImageCard({ weekKey, file, ...dropPoint })
        setCards((current) => [...current, created])
        setError(null)
      } catch (createError) {
        setError(createError instanceof Error ? createError.message : "新增图片失败")
      }
    },
    [getDropPoint, weekKey],
  )

  useEffect(() => {
    const handlePaste = (event: ClipboardEvent) => {
      const target = event.target as HTMLElement | null
      const point = textComposer ? { x: textComposer.x, y: textComposer.y } : lastCanvasPointRef.current

      const items = Array.from(event.clipboardData?.items ?? [])
      const imageItem = items.find((item) => item.kind === "file" && item.type.startsWith("image/"))
      const imageFile = imageItem?.getAsFile()
      if (imageFile) {
        event.preventDefault()
        void handleCreateImage(imageFile, point)
        return
      }

      if (target?.closest(TEXT_ENTRY_SELECTOR)) return

      const text = event.clipboardData?.getData("text/plain")
      if (text?.trim()) {
        event.preventDefault()
        void handleCreateText(text, point)
      }
    }

    window.addEventListener("paste", handlePaste)
    return () => window.removeEventListener("paste", handlePaste)
  }, [handleCreateImage, handleCreateText, textComposer])

  const handleComposerSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!textComposer) return
    void handleCreateText(textComposer.text, { x: textComposer.x, y: textComposer.y })
  }

  const handleMove = useCallback(
    (card: InspirationCard, x: number, y: number) => {
      setCards((current) => current.map((item) => (item.id === card.id ? { ...item, x, y } : item)))
      patchCard(card.id, { x, y }).then(mergeCard).catch(() => {
        setError("位置保存失败")
        void loadWeek()
      })
    },
    [loadWeek, mergeCard],
  )

  const handleDelete = useCallback(async (card: InspirationCard) => {
    try {
      await deleteCard(card.id)
      setCards((current) => current.filter((item) => item.id !== card.id))
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "删除失败")
    }
  }, [])

  const handleRetry = useCallback(
    async (card: InspirationCard) => {
      setCards((current) =>
        current.map((item) => (item.id === card.id ? { ...item, aiStatus: "pending", aiError: null } : item)),
      )
      try {
        mergeCard(await retryAnalyze(card.id))
      } catch (retryError) {
        setError(retryError instanceof Error ? retryError.message : "重试失败")
      }
    },
    [mergeCard],
  )

  const handleDeleteKeyword = useCallback(
    async (card: InspirationCard, keyword: string) => {
      const keywords = card.keywords.filter((item) => item !== keyword)
      setCards((current) => current.map((item) => (item.id === card.id ? { ...item, keywords } : item)))
      try {
        mergeCard(await patchCard(card.id, { keywords }))
      } catch (keywordError) {
        setError(keywordError instanceof Error ? keywordError.message : "关键词保存失败")
        void loadWeek()
      }
    },
    [loadWeek, mergeCard],
  )

  const handleCopyKeyword = useCallback(async (keyword: string) => {
    try {
      await navigator.clipboard.writeText(keyword)
      setToast(`已复制：${keyword}`)
    } catch {
      setToast("复制失败")
    }
  }, [])

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    const target = event.target as HTMLElement
    lastCanvasPointRef.current = clientToCanvasPoint(event.clientX, event.clientY)
    if (target.closest(BOARD_INTERACTIVE_SELECTOR)) return
    panRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: pan.x,
      originY: pan.y,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
    setIsPanning(true)
  }

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const state = panRef.current
    if (!state || state.pointerId !== event.pointerId) return
    setPan({
      x: state.originX + event.clientX - state.startX,
      y: state.originY + event.clientY - state.startY,
    })
  }

  const handlePointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (panRef.current?.pointerId !== event.pointerId) return
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    panRef.current = null
    setIsPanning(false)
  }

  const handleDoubleClick = (event: ReactMouseEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement
    if (target.closest(BOARD_INTERACTIVE_SELECTOR)) return
    const point = clientToCanvasPoint(event.clientX, event.clientY)
    lastCanvasPointRef.current = point
    setTextComposer({ ...point, text: "" })
  }

  const openImagePreview = useCallback((card: InspirationCard) => {
    setImagePreview({ card, scale: 1, x: 0, y: 0 })
  }, [])

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span>随心一记</span>
        </div>

        <div className="week-controls" aria-label="周导航">
          <Button type="button" variant="ghost" size="icon" title="上一周" onClick={() => setWeekStart(addWeeks(weekStart, -1))}>
            <ChevronLeft size={18} />
          </Button>
          <div className="week-label">
            <strong>
              {weekInfo.year} 第 {weekInfo.week} 周
            </strong>
            <span>{weekRange}</span>
          </div>
          <Button type="button" variant="ghost" size="icon" title="下一周" onClick={() => setWeekStart(addWeeks(weekStart, 1))}>
            <ChevronRight size={18} />
          </Button>
        </div>

        <div className="topbar-actions">
          <Button type="button" variant="secondary" size="sm" onClick={() => setWeekStart(getIsoWeekStart(new Date()))}>
            <CalendarDays size={16} />
            今天
          </Button>
          <Button type="button" variant="secondary" size="sm" onClick={() => void loadWeek()}>
            <RefreshCw size={16} className={isLoading ? "spin" : undefined} />
            刷新
          </Button>
        </div>
      </header>

      <main className="board-wrap">
        {cards.length === 0 && !isLoading ? <div className="empty-week">本周还空着</div> : null}

        <div
          ref={viewportRef}
          className={`canvas-viewport${isPanning ? " is-panning" : ""}`}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          onDoubleClick={handleDoubleClick}
        >
          <div className="canvas-plane" style={{ transform: `translate(${pan.x}px, ${pan.y}px)` }}>
            {textComposer ? (
              <form
                className="inline-composer"
                onSubmit={handleComposerSubmit}
                style={{ transform: `translate(${textComposer.x}px, ${textComposer.y}px)` }}
              >
                <Textarea
                  autoFocus
                  value={textComposer.text}
                  onChange={(event) => setTextComposer((current) => (current ? { ...current, text: event.target.value } : current))}
                  placeholder="写下灵感、片段或网址"
                  aria-label="文本灵感"
                />
                <div className="inline-composer-actions">
                  <Button type="button" variant="ghost" size="icon" title="关闭" onClick={() => setTextComposer(null)}>
                    <X size={15} />
                  </Button>
                  <Button type="submit" variant="primary" size="sm" disabled={!textComposer.text.trim()}>
                    <Plus size={15} />
                    添加
                  </Button>
                </div>
              </form>
            ) : null}
            {cards.map((card) => (
              <BoardCard
                key={card.id}
                card={card}
                onMove={handleMove}
                onDelete={handleDelete}
                onRetry={handleRetry}
                onCopyKeyword={handleCopyKeyword}
                onDeleteKeyword={handleDeleteKeyword}
                onOpenImage={openImagePreview}
              />
            ))}
          </div>
        </div>

        {imagePreview ? (
          <ImagePreviewOverlay
            preview={imagePreview}
            onChange={setImagePreview}
            onClose={() => setImagePreview(null)}
          />
        ) : null}
        {error ? <div className="error-banner">{error}</div> : null}
        {toast ? <div className="toast">{toast}</div> : null}
      </main>
    </div>
  )
}

export default App
