import { motion, type PanInfo } from "framer-motion"
import { Clipboard, Copy, LoaderCircle, RefreshCw, Trash2, X } from "lucide-react"

import { resolveAssetUrl } from "../lib/api"
import { hashSeed } from "../lib/utils"
import type { AiStatus, InspirationCard } from "../types"
import { Button } from "./ui/button"

const STATUS_LABEL: Record<AiStatus, string> = {
  pending: "待生成",
  generating: "生成中",
  done: "已提炼",
  failed: "待重试",
}

type BoardCardProps = {
  card: InspirationCard
  onMove: (card: InspirationCard, x: number, y: number) => void
  onDelete: (card: InspirationCard) => void
  onRetry: (card: InspirationCard) => void
  onCopyKeyword: (keyword: string) => void
  onDeleteKeyword: (card: InspirationCard, keyword: string) => void
  onOpenImage: (card: InspirationCard) => void
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
  const seed = hashSeed(card.styleSeed)
  const palette = seed % 4
  const decoration = seed % 4
  const className = card.type === "text" ? `inspiration-card text-card palette-${palette}` : "inspiration-card image-card"

  const handleDragEnd = (_event: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
    onMove(card, Math.round(card.x + info.offset.x), Math.round(card.y + info.offset.y))
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
            <Button type="button" variant="ghost" size="icon" title="重试 AI" onClick={() => onRetry(card)}>
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
              alt={card.summary || "灵感截图"}
              draggable={false}
              onDoubleClick={(event) => {
                event.stopPropagation()
                onOpenImage(card)
              }}
            />
          </div>
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
  card: InspirationCard
  onCopyKeyword: (keyword: string) => void
  onDeleteKeyword: (keyword: string) => void
}) {
  if (card.keywords.length === 0) {
    return (
      <div className="keyword-area">
        <span className={`status-pill ${card.aiStatus}`}>
          {card.aiStatus === "pending" || card.aiStatus === "generating" ? <LoaderCircle size={13} className="spin" /> : null}
          {card.aiStatus === "failed" ? <Clipboard size={13} /> : null}
          {STATUS_LABEL[card.aiStatus]}
        </span>
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
