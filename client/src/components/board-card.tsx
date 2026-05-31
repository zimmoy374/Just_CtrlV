import { motion, type PanInfo } from "framer-motion"
import { Clipboard, Copy, ExternalLink, Link, LoaderCircle, RefreshCw, Trash2, X } from "lucide-react"

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
  isHighlighted?: boolean
  onMove: (card: CaptureCard, x: number, y: number) => void
  onDelete: (card: CaptureCard) => void
  onRetry: (card: CaptureCard) => void
  onCopyKeyword: (keyword: string) => void
  onDeleteKeyword: (card: CaptureCard, keyword: string) => void
  onOpenImage: (card: CaptureCard) => void
  canvasScale: number
}

export function BoardCard({
  card,
  isHighlighted = false,
  onMove,
  onDelete,
  onRetry,
  onCopyKeyword,
  onDeleteKeyword,
  onOpenImage,
  canvasScale,
}: BoardCardProps) {
  const seed = hashSeed(card.styleSeed)
  const palette = seed % 8
  const decoration = seed % 8
  const baseClass =
    card.type === "image" ? "capture-card image-card" : card.type === "link" ? "capture-card link-card" : `capture-card text-card palette-${palette}`
  const className = `${baseClass}${isHighlighted ? " is-highlighted" : ""}`

  const handleDragEnd = (_event: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
    onMove(card, Math.round(card.x + info.offset.x / canvasScale), Math.round(card.y + info.offset.y / canvasScale))
  }

  return (
    <motion.article
      className={className}
      drag
      dragMomentum={false}
      style={{ x: card.x, y: card.y, rotate: `${card.rotation}deg`, width: card.width }}
      onDragEnd={handleDragEnd}
      tabIndex={0}
    >
      <span className={`decor decor-${decoration}`} />
      <div className="card-inner">
        <div className="card-actions">
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
        ) : (
          <p className="text-content">{card.textContent}</p>
        )}

        {card.summary ? <p className="card-summary">{card.summary}</p> : null}

        <KeywordArea
          card={card}
          onCopyKeyword={onCopyKeyword}
          onDeleteKeyword={(keyword) => onDeleteKeyword(card, keyword)}
        />
      </div>
    </motion.article>
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


