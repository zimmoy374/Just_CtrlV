import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type {
  Dispatch,
  FormEvent,
  MouseEvent as ReactMouseEvent,
  PointerEvent as ReactPointerEvent,
  SetStateAction,
} from "react"

import { createImageCard, createLinkCard, createTextCard, deleteCard, listCards, patchCard, retryAnalyze } from "../lib/api/cards"
import { addWeeks, formatWeekRange, getIsoWeekInfo, getIsoWeekStart, getWeekKey, getWeekStartFromKey } from "../lib/dates"
import type { CaptureCard } from "../types/cards"
import type { ImagePreviewState } from "../components/image-preview-overlay"
import type { Point, TextComposer } from "../pages/BoardPage"
import type { AppView } from "./useKnowledgeWorkspace"

type PanState = {
  pointerId: number
  startX: number
  startY: number
  originX: number
  originY: number
}

type BoardNotifications = {
  view: AppView
  setView: Dispatch<SetStateAction<AppView>>
  setError: (value: string | null) => void
  setToast: (value: string | null) => void
  refreshReflections: () => Promise<void>
}

const BOARD_INTERACTIVE_SELECTOR = ".capture-card,.inline-composer,button,textarea,input"
const TEXT_ENTRY_SELECTOR = "textarea,input,[contenteditable='true']"

export function useBoardController({ view, setView, setError, setToast, refreshReflections }: BoardNotifications) {
  const [weekStart, setWeekStart] = useState(() => getIsoWeekStart(new Date()))
  const [cards, setCards] = useState<CaptureCard[]>([])
  const [textComposer, setTextComposer] = useState<TextComposer | null>(null)
  const [pan, setPan] = useState<Point>({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [isPanning, setIsPanning] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [imagePreview, setImagePreview] = useState<ImagePreviewState | null>(null)
  const [highlightedCardId, setHighlightedCardId] = useState<string | null>(null)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const panRef = useRef<PanState | null>(null)
  const lastCanvasPointRef = useRef<Point | null>(null)

  const weekKey = useMemo(() => getWeekKey(weekStart), [weekStart])
  const weekInfo = useMemo(() => getIsoWeekInfo(weekStart), [weekStart])
  const weekRange = useMemo(() => formatWeekRange(weekStart), [weekStart])
  const weekTitle = `${weekInfo.year} 第 ${weekInfo.week} 周`

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
  }, [setError, weekKey])

  const clientToCanvasPoint = useCallback(
    (clientX: number, clientY: number): Point => {
      const rect = viewportRef.current?.getBoundingClientRect()
      return {
        x: Math.max(24, (clientX - (rect?.left ?? 0) - pan.x) / zoom),
        y: Math.max(24, (clientY - (rect?.top ?? 0) - pan.y) / zoom),
      }
    },
    [pan.x, pan.y, zoom],
  )

  const getDropPoint = useCallback(
    (preferred?: Point | null): Point => {
      if (preferred) return preferred
      const rect = viewportRef.current?.getBoundingClientRect()
      const offset = (cards.length % 8) * 26
      return {
        x: Math.max(48, ((rect?.width ?? 1200) / 2 - pan.x - 160 + offset) / zoom),
        y: Math.max(84, ((rect?.height ?? 720) / 2 - pan.y - 130 + offset / 2) / zoom),
      }
    },
    [cards.length, pan.x, pan.y, zoom],
  )

  const mergeCard = useCallback((updated: CaptureCard) => {
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
    [getDropPoint, setError, weekKey],
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
    [getDropPoint, setError, weekKey],
  )

  const handleCreateLink = useCallback(
    async (url: string, point?: Point | null) => {
      const trimmed = url.trim()
      if (!trimmed) return
      const dropPoint = getDropPoint(point)
      try {
        const created = await createLinkCard({ weekKey, url: trimmed, ...dropPoint })
        setCards((current) => [...current, created])
        setTextComposer(null)
        setError(null)
      } catch (createError) {
        setError(createError instanceof Error ? createError.message : "新增链接失败")
      }
    },
    [getDropPoint, setError, weekKey],
  )

  const handleComposerSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      if (!textComposer) return
      const trimmed = textComposer.text.trim()
      if (isProbablyUrl(trimmed)) {
        void handleCreateLink(trimmed, { x: textComposer.x, y: textComposer.y })
        return
      }
      void handleCreateText(trimmed, { x: textComposer.x, y: textComposer.y })
    },
    [handleCreateLink, handleCreateText, textComposer],
  )

  const handleMove = useCallback(
    (card: CaptureCard, x: number, y: number) => {
      setCards((current) => current.map((item) => (item.id === card.id ? { ...item, x, y } : item)))
      patchCard(card.id, { x, y })
        .then(mergeCard)
        .catch(() => {
          setError("位置保存失败")
          void loadWeek()
        })
    },
    [loadWeek, mergeCard, setError],
  )

  const handleDelete = useCallback(
    async (card: CaptureCard) => {
      try {
        await deleteCard(card.id)
        setCards((current) => current.filter((item) => item.id !== card.id))
      } catch (deleteError) {
        setError(deleteError instanceof Error ? deleteError.message : "删除失败")
      }
    },
    [setError],
  )

  const handleRetry = useCallback(
    async (card: CaptureCard) => {
      setCards((current) =>
        current.map((item) => (item.id === card.id ? { ...item, aiStatus: "pending", aiError: null } : item)),
      )
      try {
        mergeCard(await retryAnalyze(card.id))
      } catch (retryError) {
        setError(retryError instanceof Error ? retryError.message : "重试失败")
      }
    },
    [mergeCard, setError],
  )

  const handleDeleteKeyword = useCallback(
    async (card: CaptureCard, keyword: string) => {
      const keywords = card.keywords.filter((item) => item !== keyword)
      setCards((current) => current.map((item) => (item.id === card.id ? { ...item, keywords } : item)))
      try {
        mergeCard(await patchCard(card.id, { keywords }))
      } catch (keywordError) {
        setError(keywordError instanceof Error ? keywordError.message : "关键词保存失败")
        void loadWeek()
      }
    },
    [loadWeek, mergeCard, setError],
  )

  const handleCopyKeyword = useCallback(
    async (keyword: string) => {
      try {
        await navigator.clipboard.writeText(keyword)
        setToast(`已复制：${keyword}`)
      } catch {
        setToast("复制失败")
      }
    },
    [setToast],
  )

  const goToday = useCallback(() => {
    setWeekStart(getIsoWeekStart(new Date()))
    setTextComposer(null)
    setHighlightedCardId(null)
    setView("board")
  }, [setView])

  const openCardWeek = useCallback(
    (card: CaptureCard) => {
      setWeekStart(getWeekStartFromKey(card.weekKey))
      setTextComposer(null)
      setHighlightedCardId(card.id)
      setView("board")
    },
    [setView],
  )

  const handlePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
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
    },
    [clientToCanvasPoint, pan.x, pan.y],
  )

  const handlePointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const state = panRef.current
    if (!state || state.pointerId !== event.pointerId) return
    setPan({
      x: state.originX + event.clientX - state.startX,
      y: state.originY + event.clientY - state.startY,
    })
  }, [])

  const handlePointerUp = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (panRef.current?.pointerId !== event.pointerId) return
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    panRef.current = null
    setIsPanning(false)
  }, [])

  const handleDoubleClick = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      const target = event.target as HTMLElement
      if (target.closest(BOARD_INTERACTIVE_SELECTOR)) return
      const point = clientToCanvasPoint(event.clientX, event.clientY)
      lastCanvasPointRef.current = point
      setTextComposer({ ...point, text: "" })
    },
    [clientToCanvasPoint],
  )

  const openImagePreview = useCallback((card: CaptureCard) => {
    setImagePreview({ card, scale: 1, x: 0, y: 0 })
  }, [])

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
      void refreshReflections()
    }, 2200)
    return () => window.clearInterval(timer)
  }, [cards, loadWeek, refreshReflections])

  useEffect(() => {
    if (!highlightedCardId) return
    const timer = window.setTimeout(() => setHighlightedCardId(null), 2600)
    return () => window.clearTimeout(timer)
  }, [highlightedCardId])

  useEffect(() => {
    if (!highlightedCardId || view !== "board") return
    const card = cards.find((item) => item.id === highlightedCardId)
    const rect = viewportRef.current?.getBoundingClientRect()
    if (!card || !rect) return
    setPan({
      x: Math.round(rect.width / 2 - card.x - card.width / 2),
      y: Math.round(rect.height / 2 - card.y - 120),
    })
  }, [cards, highlightedCardId, view])

  useEffect(() => {
    const handlePaste = (event: ClipboardEvent) => {
      if (view !== "board") return
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
      const trimmed = text?.trim()
      if (trimmed && isProbablyUrl(trimmed)) {
        event.preventDefault()
        void handleCreateLink(trimmed, point)
        return
      }

      if (trimmed) {
        event.preventDefault()
        void handleCreateText(trimmed, point)
      }
    }

    window.addEventListener("paste", handlePaste)
    return () => window.removeEventListener("paste", handlePaste)
  }, [handleCreateImage, handleCreateLink, handleCreateText, textComposer, view])

  useEffect(() => {
    const element = viewportRef.current
    if (!element) return

    const handleWheel = (event: WheelEvent) => {
      if (view !== "board") return
      const target = event.target as HTMLElement | null
      if (target?.closest(BOARD_INTERACTIVE_SELECTOR)) return
      event.preventDefault()
      setZoom((current) => Math.min(2.2, Math.max(0.5, Number((current - event.deltaY * 0.0012).toFixed(3)))))
    }

    element.addEventListener("wheel", handleWheel, { passive: false })
    return () => element.removeEventListener("wheel", handleWheel)
  }, [view])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (view !== "board") return
      if (event.ctrlKey && event.key === "=") {
        event.preventDefault()
        setZoom((current) => Math.min(2.2, Number((current + 0.1).toFixed(3))))
      }
      if (event.ctrlKey && event.key === "-") {
        event.preventDefault()
        setZoom((current) => Math.max(0.5, Number((current - 0.1).toFixed(3))))
      }
      if (event.ctrlKey && event.key === "0") {
        event.preventDefault()
        setZoom(1)
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [view])

  return {
    weekStart,
    setWeekStart,
    weekTitle,
    weekRange,
    cards,
    isLoading,
    isPanning,
    viewportRef,
    pan,
    zoom,
    textComposer,
    setTextComposer,
    highlightedCardId,
    imagePreview,
    setImagePreview,
    handleComposerSubmit,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handleDoubleClick,
    handleMove,
    handleDelete,
    handleRetry,
    handleCopyKeyword,
    handleDeleteKeyword,
    openImagePreview,
    openCardWeek,
    goToday,
    addWeeks,
  }
}

function isProbablyUrl(value: string) {
  return /^(https?:\/\/|www\.)\S+/i.test(value)
}
