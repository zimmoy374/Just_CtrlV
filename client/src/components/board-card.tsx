import { useRef, useState } from "react"
import type { PointerEvent as ReactPointerEvent } from "react"
import { ChevronDown, ChevronUp, Clipboard, Copy, ExternalLink, Link, LoaderCircle, RefreshCw, Trash2, X } from "lucide-react"

import { resolveAssetUrl } from "../lib/api/client"
import { hashSeed } from "../lib/utils"
import type { AiStatus, CaptureCard } from "../types/cards"
import { Button } from "./ui/button"

const STATUS_LABEL: Record<AiStatus, string> = {
  pending: "待生成",
  generating: "生成中",
  done: "已提炼",
  failed: "待重试",
}

type BoardCardProps = {
  card: CaptureCard
  onMove: (card: CaptureCard, deltaX: number, deltaY: number) => void
  onDelete: (card: CaptureCard) => void
  onRetry: (card: CaptureCard) => void
  onCopyKeyword: (keyword: string) => void
  onDeleteKeyword: (card: CaptureCard, keyword: string) => void
  onOpenImage: (card: CaptureCard) => void
}

export function BoardCard({
  card,
  onMove,
  onDelete,
  onRetry,
  onCopyKeyword,
  onDeleteKeyword,
  onOpenImage,
}: BoardCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })
  const dragRef = useRef<{ pointerId: number; startX: number; startY: number } | null>(null)
  const seed = hashSeed(card.styleSeed)
  const palette = seed % 8
  const hasSummary = Boolean(card.summary?.trim())
  const canExpand = card.type === "text" && hasSummary && Boolean(card.textContent?.trim())
  const baseClass =
    card.type === "image" ? "capture-card image-card" : card.type === "link" ? "capture-card link-card" : `capture-card text-card palette-${palette}`
  const className = `${baseClass}${isDragging ? " is-dragging" : ""}`

  const handlePointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0 || (event.target as HTMLElement).closest("button,a")) return
    event.currentTarget.setPointerCapture(event.pointerId)
    dragRef.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY }
    setIsDragging(true)
  }

  const handlePointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    setDragOffset({ x: event.clientX - drag.startX, y: event.clientY - drag.startY })
  }

  const handlePointerUp = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    const deltaX = event.clientX - drag.startX
    const deltaY = event.clientY - drag.startY
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    dragRef.current = null
    setIsDragging(false)
    setDragOffset({ x: 0, y: 0 })
    if (Math.abs(deltaX) > 2 || Math.abs(deltaY) > 2) onMove(card, deltaX, deltaY)
  }

  return (
    <article
      className={className}
      style={{
        left: `${card.x * 100}%`,
        top: `${card.y * 100}%`,
        width: card.width,
        transform: `translate(${dragOffset.x}px, ${dragOffset.y}px) rotate(${card.rotation}deg)`,
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      tabIndex={0}
    >
      <div className="card-inner">
        <div className="card-actions">
          {canExpand ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              title={isExpanded ? "收起原文" : "展开原文"}
              aria-expanded={isExpanded}
              onClick={() => setIsExpanded((current) => !current)}
            >
              {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </Button>
          ) : null}
          {card.aiStatus === "failed" ? (
            <Button type="button" variant="ghost" size="icon" title="重试智能整理" onClick={() => onRetry(card)}>
              <RefreshCw size={15} />
            </Button>
          ) : null}
          <Button type="button" variant="ghost" size="icon" title="删除卡片" onClick={() => onDelete(card)}>
            <Trash2 size={15} />
          </Button>
        </div>

        {card.type === "image" ? (
          <div className="image-frame">
            <img
              src={resolveAssetUrl(card.imageUrl)}
              alt={card.summary || "知识截图"}
              draggable={false}
              onDoubleClick={(event) => {
                event.stopPropagation()
                onOpenImage(card)
              }}
            />
          </div>
        ) : card.type === "link" ? (
          <a className="link-preview" href={card.sourceUrl || "#"} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
            <span className="link-preview-icon">
              <Link size={18} />
            </span>
            <strong>{card.sourceTitle || card.sourceUrl || "链接"}</strong>
            {card.sourceDescription ? <span>{card.sourceDescription}</span> : null}
            <em>
              打开链接
              <ExternalLink size={13} />
            </em>
          </a>
        ) : card.type === "text" ? (
          <>
            {hasSummary ? <p className="card-summary card-summary-primary">{card.summary}</p> : null}
            {!hasSummary || isExpanded ? (
              <div className={`raw-content${hasSummary ? " is-expanded" : ""}`}>
                {hasSummary ? <span>原文</span> : null}
                <p className="text-content">{card.textContent}</p>
              </div>
            ) : null}
          </>
        ) : (
          <p className="text-content">{card.textContent}</p>
        )}

        {card.type !== "text" && card.summary ? <p className="card-summary">{card.summary}</p> : null}

        <KeywordArea
          card={card}
          onCopyKeyword={onCopyKeyword}
          onDeleteKeyword={(keyword) => onDeleteKeyword(card, keyword)}
        />
      </div>
    </article>
  )
}

function KeywordArea({
  card,
  onCopyKeyword,
  onDeleteKeyword,
}: {
  card: CaptureCard
  onCopyKeyword: (keyword: string) => void
  onDeleteKeyword: (keyword: string) => void
}) {
  if (card.keywords.length === 0) {
    return (
      <div className="keyword-area">
        <span className={`status-pill ${card.aiStatus}`} title={card.aiError || STATUS_LABEL[card.aiStatus]}>
          {card.aiStatus === "pending" || card.aiStatus === "generating" ? <LoaderCircle size={13} className="spin" /> : null}
          {card.aiStatus === "failed" ? <Clipboard size={13} /> : null}
          {STATUS_LABEL[card.aiStatus]}
        </span>
        {card.aiStatus === "failed" && card.aiError ? <p className="ai-error-text">{card.aiError}</p> : null}
      </div>
    )
  }

  const firstKeyword = card.keywords[0]
  const extraCount = Math.max(0, card.keywords.length - 1)

  return (
    <div className="keyword-area">
      <button type="button" className="keyword-compact" title="复制关键词" onClick={() => onCopyKeyword(firstKeyword)}>
        <Copy size={13} />
        <span>{firstKeyword}</span>
        {extraCount > 0 ? <strong className="keyword-count">+{extraCount}</strong> : null}
      </button>
      <div className="keyword-expanded">
        {card.keywords.map((keyword) => (
          <span className="keyword-token" key={keyword}>
            <button type="button" className="keyword-copy" title="复制关键词" onClick={() => onCopyKeyword(keyword)}>
              <span>{keyword}</span>
            </button>
            <button type="button" className="delete-keyword" title="删除关键词" onClick={() => onDeleteKeyword(keyword)}>
              <X size={13} />
            </button>
          </span>
        ))}
      </div>
    </div>
  )
}


