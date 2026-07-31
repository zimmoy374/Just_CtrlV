import type { FormEvent, MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, RefObject } from "react"
import { Plus, X } from "lucide-react"

import { BoardCard } from "../components/board-card"
import { Button } from "../components/ui/button"
import { Textarea } from "../components/ui/textarea"
import type { CaptureCard } from "../types/cards"

export type Point = { x: number; y: number }
export type TextComposer = Point & { text: string }

type BoardPageProps = {
  cards: CaptureCard[]
  isLoading: boolean
  viewportRef: RefObject<HTMLDivElement>
  textComposer: TextComposer | null
  onTextComposerChange: (value: TextComposer | null | ((current: TextComposer | null) => TextComposer | null)) => void
  onComposerSubmit: (event: FormEvent<HTMLFormElement>) => void
  onPointerMove: (event: ReactPointerEvent<HTMLDivElement>) => void
  onDoubleClick: (event: ReactMouseEvent<HTMLDivElement>) => void
  onMove: (card: CaptureCard, deltaX: number, deltaY: number) => void
  onDelete: (card: CaptureCard) => void
  onRetry: (card: CaptureCard) => void
  onCopyKeyword: (keyword: string) => void
  onDeleteKeyword: (card: CaptureCard, keyword: string) => void
  onOpenImage: (card: CaptureCard) => void
}

export function BoardPage({
  cards,
  isLoading,
  viewportRef,
  textComposer,
  onTextComposerChange,
  onComposerSubmit,
  onPointerMove,
  onDoubleClick,
  onMove,
  onDelete,
  onRetry,
  onCopyKeyword,
  onDeleteKeyword,
  onOpenImage,
}: BoardPageProps) {
  return (
    <div
      ref={viewportRef}
      className="daily-desk"
      aria-busy={isLoading}
      onPointerMove={onPointerMove}
      onDoubleClick={onDoubleClick}
    >
      {textComposer ? (
        <form
          className="inline-composer"
          onSubmit={onComposerSubmit}
          style={{ left: `${textComposer.x * 100}%`, top: `${textComposer.y * 100}%` }}
        >
          <Textarea
            autoFocus
            value={textComposer.text}
            onChange={(event) => onTextComposerChange((current) => (current ? { ...current, text: event.target.value } : current))}
            placeholder="记录内容"
            aria-label="保存文本"
          />
          <div className="inline-composer-actions">
            <Button type="button" variant="ghost" size="icon" title="关闭" onClick={() => onTextComposerChange(null)}>
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
          onMove={onMove}
          onDelete={onDelete}
          onRetry={onRetry}
          onCopyKeyword={onCopyKeyword}
          onDeleteKeyword={onDeleteKeyword}
          onOpenImage={onOpenImage}
        />
      ))}
    </div>
  )
}
