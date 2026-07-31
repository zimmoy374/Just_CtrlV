import { useCallback, useEffect, useRef, useState } from "react"
import type { FormEvent, MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent } from "react"

import type { ImagePreviewState } from "../components/image-preview-overlay"
import {
  createImageCard,
  createLinkCard,
  createTextCard,
  deleteCard,
  listActiveDays,
  listCards,
  patchCard,
  retryAnalyze,
} from "../lib/api/cards"
import type { Point, TextComposer } from "../pages/BoardPage"
import type { CaptureCard } from "../types/cards"

type BoardNotifications = {
  setError: (value: string | null) => void
  setToast: (value: string | null) => void
}

const BOARD_INTERACTIVE_SELECTOR = ".capture-card,.inline-composer,.paw-menu,.calendar-dialog,button,textarea,input,a"
const TEXT_ENTRY_SELECTOR = "textarea,input,[contenteditable='true']"
const CARD_GAP_PX = 22

export function useBoardController({ setError, setToast }: BoardNotifications) {
  const todayKey = localDayKey(new Date())
  const [selectedDay, setSelectedDayState] = useState(todayKey)
  const [availableDays, setAvailableDays] = useState<string[]>([])
  const [cards, setCards] = useState<CaptureCard[]>([])
  const [textComposer, setTextComposer] = useState<TextComposer | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [needsReconnect, setNeedsReconnect] = useState(false)
  const [imagePreview, setImagePreview] = useState<ImagePreviewState | null>(null)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const lastBoardPointRef = useRef<Point | null>(null)

  const refreshAvailableDays = useCallback(async () => {
    const days = await listActiveDays()
    setAvailableDays(days)
    return days
  }, [])

  const loadDay = useCallback(async () => {
    try {
      setIsLoading(true)
      const [dayCards] = await Promise.all([listCards(selectedDay), refreshAvailableDays()])
      setCards(dayCards)
      setNeedsReconnect(false)
      setError(null)
    } catch (loadError) {
      setNeedsReconnect(true)
      setError(loadError instanceof Error ? loadError.message : "加载失败")
    } finally {
      setIsLoading(false)
    }
  }, [refreshAvailableDays, selectedDay, setError])

  const setSelectedDay = useCallback((dayKey: string) => {
    setSelectedDayState(dayKey)
    setTextComposer(null)
    setImagePreview(null)
    lastBoardPointRef.current = null
  }, [])

  const clientToBoardPoint = useCallback((clientX: number, clientY: number): Point => {
    const rect = viewportRef.current?.getBoundingClientRect()
    if (!rect) return { x: 0.36, y: 0.3 }
    return {
      x: clamp((clientX - rect.left) / rect.width, 0.03, 0.97),
      y: clamp((clientY - rect.top) / rect.height, 0.04, 0.96),
    }
  }, [])

  const getDropPoint = useCallback(
    (preferred: Point | null | undefined, cardType: CaptureCard["type"]): Point => {
      const rect = viewportRef.current?.getBoundingClientRect()
      const origin = preferred ?? { x: 0.38, y: 0.3 }
      return findNearestOpenPoint(origin, cardType, cards, rect?.width || 1280, rect?.height || 720)
    },
    [cards],
  )

  const mergeCard = useCallback((updated: CaptureCard) => {
    setCards((current) => current.map((card) => (card.id === updated.id ? updated : card)))
  }, [])

  const finishCreate = useCallback(async (created: CaptureCard) => {
    setCards((current) => [...current, created])
    setTextComposer(null)
    setError(null)
    await refreshAvailableDays()
  }, [refreshAvailableDays, setError])

  const handleCreateText = useCallback(async (text: string, point?: Point | null) => {
    const trimmed = text.trim()
    if (!trimmed) return
    try {
      await finishCreate(
        await createTextCard({ dayKey: selectedDay, textContent: trimmed, ...getDropPoint(point, "text") }),
      )
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "新增文本失败")
    }
  }, [finishCreate, getDropPoint, selectedDay, setError])

  const handleCreateImage = useCallback(async (file: File, point?: Point | null) => {
    try {
      await finishCreate(await createImageCard({ dayKey: selectedDay, file, ...getDropPoint(point, "image") }))
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "新增图片失败")
    }
  }, [finishCreate, getDropPoint, selectedDay, setError])

  const handleCreateLink = useCallback(async (url: string, point?: Point | null) => {
    const trimmed = url.trim()
    if (!trimmed) return
    try {
      await finishCreate(await createLinkCard({ dayKey: selectedDay, url: trimmed, ...getDropPoint(point, "link") }))
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "新增链接失败")
    }
  }, [finishCreate, getDropPoint, selectedDay, setError])

  const handleComposerSubmit = useCallback((event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!textComposer) return
    const value = textComposer.text.trim()
    if (isProbablyUrl(value)) void handleCreateLink(value, textComposer)
    else void handleCreateText(value, textComposer)
  }, [handleCreateLink, handleCreateText, textComposer])

  const handleMove = useCallback((card: CaptureCard, deltaX: number, deltaY: number) => {
    const rect = viewportRef.current?.getBoundingClientRect()
    if (!rect) return
    const maxX = Math.max(0.03, 1 - Math.min(card.width, rect.width - 24) / rect.width - 0.03)
    const estimatedHeight = estimateCardHeightPx(card)
    const maxY = Math.max(0.04, 1 - Math.min(estimatedHeight, rect.height - 24) / rect.height - 0.04)
    const x = clamp(card.x + deltaX / rect.width, 0.03, maxX)
    const y = clamp(card.y + deltaY / rect.height, 0.04, maxY)
    setCards((current) => current.map((item) => (item.id === card.id ? { ...item, x, y } : item)))
    patchCard(card.id, { x, y }).then(mergeCard).catch(() => {
      setError("位置保存失败")
      void loadDay()
    })
  }, [loadDay, mergeCard, setError])

  const handleDelete = useCallback(async (card: CaptureCard) => {
    try {
      await deleteCard(card.id)
      setCards((current) => current.filter((item) => item.id !== card.id))
      await refreshAvailableDays()
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "删除失败")
    }
  }, [refreshAvailableDays, setError])

  const handleRetry = useCallback(async (card: CaptureCard) => {
    setCards((current) => current.map((item) => (item.id === card.id ? { ...item, aiStatus: "pending", aiError: null } : item)))
    try {
      mergeCard(await retryAnalyze(card.id))
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "重试失败")
    }
  }, [mergeCard, setError])

  const handleDeleteKeyword = useCallback(async (card: CaptureCard, keyword: string) => {
    const keywords = card.keywords.filter((item) => item !== keyword)
    setCards((current) => current.map((item) => (item.id === card.id ? { ...item, keywords } : item)))
    try {
      mergeCard(await patchCard(card.id, { keywords }))
    } catch {
      setError("关键词保存失败")
      void loadDay()
    }
  }, [loadDay, mergeCard, setError])

  const handleCopyKeyword = useCallback(async (keyword: string) => {
    try {
      await navigator.clipboard.writeText(keyword)
      setToast(`已复制：${keyword}`)
    } catch {
      setToast("复制失败")
    }
  }, [setToast])

  const handleBoardPointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest(BOARD_INTERACTIVE_SELECTOR)) return
    lastBoardPointRef.current = clientToBoardPoint(event.clientX, event.clientY)
  }, [clientToBoardPoint])

  const handleDoubleClick = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest(BOARD_INTERACTIVE_SELECTOR)) return
    const point = clientToBoardPoint(event.clientX, event.clientY)
    lastBoardPointRef.current = point
    setTextComposer({ ...point, text: "" })
  }, [clientToBoardPoint])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadDay(), 0)
    return () => window.clearTimeout(timer)
  }, [loadDay])

  useEffect(() => {
    if (!needsReconnect) return
    const timer = window.setTimeout(() => void loadDay(), 2500)
    return () => window.clearTimeout(timer)
  }, [loadDay, needsReconnect])

  useEffect(() => {
    if (!cards.some((card) => card.aiStatus === "pending" || card.aiStatus === "generating")) return
    const timer = window.setInterval(() => void loadDay(), 2200)
    return () => window.clearInterval(timer)
  }, [cards, loadDay])

  useEffect(() => {
    const handlePaste = (event: ClipboardEvent) => {
      const target = event.target instanceof Element ? event.target : null
      const point = textComposer ? { x: textComposer.x, y: textComposer.y } : lastBoardPointRef.current
      const image = Array.from(event.clipboardData?.items ?? [])
        .find((item) => item.kind === "file" && item.type.startsWith("image/"))?.getAsFile()
      if (image) {
        event.preventDefault()
        void handleCreateImage(image, point)
        return
      }
      if (target?.closest(TEXT_ENTRY_SELECTOR)) return
      const text = event.clipboardData?.getData("text/plain")?.trim()
      if (!text) return
      event.preventDefault()
      if (isProbablyUrl(text)) void handleCreateLink(text, point)
      else void handleCreateText(text, point)
    }
    window.addEventListener("paste", handlePaste)
    return () => window.removeEventListener("paste", handlePaste)
  }, [handleCreateImage, handleCreateLink, handleCreateText, textComposer])

  return {
    todayKey,
    selectedDay,
    setSelectedDay,
    availableDays,
    cards,
    isLoading,
    viewportRef,
    textComposer,
    setTextComposer,
    imagePreview,
    setImagePreview,
    handleComposerSubmit,
    handleBoardPointerMove,
    handleDoubleClick,
    handleMove,
    handleDelete,
    handleRetry,
    handleCopyKeyword,
    handleDeleteKeyword,
    openImagePreview: (card: CaptureCard) => setImagePreview({ card, scale: 1, x: 0, y: 0 }),
  }
}

function isProbablyUrl(value: string) {
  return /^(https?:\/\/|www\.)\S+/i.test(value)
}

export function localDayKey(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, "0")
  const day = String(value.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function findNearestOpenPoint(
  origin: Point,
  cardType: CaptureCard["type"],
  cards: CaptureCard[],
  viewportWidth: number,
  viewportHeight: number,
): Point {
  const width = Math.min(cardType === "link" ? 320 : cardType === "text" ? 300 : 280, viewportWidth - 32) / viewportWidth
  const height = (cardType === "image" ? 350 : cardType === "link" ? 220 : 190) / viewportHeight
  const gapX = CARD_GAP_PX / viewportWidth
  const gapY = CARD_GAP_PX / viewportHeight
  const clampPoint = (point: Point) => ({
    x: clamp(point.x, 0.03, Math.max(0.03, 0.97 - width)),
    y: clamp(point.y, 0.04, Math.max(0.04, 0.96 - height)),
  })
  const candidates = [origin, ...cards.flatMap((card) => {
    const cardWidth = Math.min(card.width, viewportWidth - 32) / viewportWidth
    const cardHeight = estimateCardHeightPx(card) / viewportHeight
    return [
      { x: card.x + cardWidth + gapX, y: card.y },
      { x: card.x, y: card.y + cardHeight + gapY },
      { x: card.x - width - gapX, y: card.y },
      { x: card.x, y: card.y - height - gapY },
    ]
  })]
    .map(clampPoint)
    .sort((a, b) => distanceSquared(a, origin) - distanceSquared(b, origin))

  for (const candidate of candidates) {
    if (isOpenSpace(candidate, width, height, cards, viewportWidth, viewportHeight)) return candidate
  }

  const fallbackIndex = Math.max(0, cards.length - 8)
  return clampPoint({ x: 0.64 + fallbackIndex * 0.008, y: 0.64 + fallbackIndex * 0.008 })
}

function isOpenSpace(
  point: Point,
  width: number,
  height: number,
  cards: CaptureCard[],
  viewportWidth: number,
  viewportHeight: number,
) {
  const gapX = CARD_GAP_PX / viewportWidth
  const gapY = CARD_GAP_PX / viewportHeight
  return cards.every((card) => {
    const cardWidth = Math.min(card.width, viewportWidth - 32) / viewportWidth
    const cardHeight = estimateCardHeightPx(card) / viewportHeight
    return (
      point.x + width + gapX <= card.x ||
      point.x >= card.x + cardWidth + gapX ||
      point.y + height + gapY <= card.y ||
      point.y >= card.y + cardHeight + gapY
    )
  })
}

function estimateCardHeightPx(card: CaptureCard) {
  if (card.type === "image") return 350
  if (card.type === "link") return 220
  if (card.summary) return 160
  const textLength = card.textContent?.length ?? 0
  return Math.min(390, Math.max(160, 110 + Math.ceil(textLength / 80) * 26))
}

function distanceSquared(a: Point, b: Point) {
  return (a.x - b.x) ** 2 + (a.y - b.y) ** 2
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value))
}
