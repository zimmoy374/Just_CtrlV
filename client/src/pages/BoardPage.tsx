import type { FormEvent, MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, RefObject } from "react"
import { Plus, X } from "lucide-react"

import type { CaptureCard } from "../types/cards"
import { BoardCard } from "../components/board-card"
import { Button } from "../components/ui/button"
import { Textarea } from "../components/ui/textarea"

export type Point = {
  x: number
  y: number
}

export type TextComposer = Point & {
  text: string
}

type BoardPageProps = {
  cards: CaptureCard[]
  isLoading: boolean
  isPanning: boolean
  viewportRef: RefObject<HTMLDivElement>
  pan: Point
  zoom: number
  textComposer: TextComposer | null
  highlightedCardId: string | null
  onTextComposerChange: (value: TextComposer | null | ((current: TextComposer | null) => TextComposer | null)) => void
  onComposerSubmit: (event: FormEvent<HTMLFormElement>) => void
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void
  onPointerMove: (event: ReactPointerEvent<HTMLDivElement>) => void
  onPointerUp: (event: ReactPointerEvent<HTMLDivElement>) => void
  onDoubleClick: (event: ReactMouseEvent<HTMLDivElement>) => void
  onMove: (card: CaptureCard, x: number, y: number) => void
  onDelete: (card: CaptureCard) => void
  onRetry: (card: CaptureCard) => void
  onCopyKeyword: (keyword: string) => void
  onDeleteKeyword: (card: CaptureCard, keyword: string) => void
  onOpenImage: (card: CaptureCard) => void
}

export function BoardPage({
  cards,
  isLoading,
  isPanning,
  viewportRef,
  pan,
  zoom,
  textComposer,
  highlightedCardId,
  onTextComposerChange,
  onComposerSubmit,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onDoubleClick,
  onMove,
  onDelete,
  onRetry,
  onCopyKeyword,
  onDeleteKeyword,
  onOpenImage,
}: BoardPageProps) {
  return (
    <>
      {cards.length === 0 && !isLoading ? <div className="empty-week">本周还空着</div> : null}

      <div
        ref={viewportRef}
        className={`canvas-viewport${isPanning ? " is-panning" : ""}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={onDoubleClick}
      >
        <div className="canvas-plane" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
          {textComposer ? (
            <form className="inline-composer" onSubmit={onComposerSubmit} style={{ transform: `translate(${textComposer.x}px, ${textComposer.y}px)` }}>
              <Textarea
                autoFocus
                value={textComposer.text}
                onChange={(event) =>
                  onTextComposerChange((current) => (current ? { ...current, text: event.target.value } : current))
                }
                placeholder="保存想法、片段或网址"
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
              isHighlighted={card.id === highlightedCardId}
              onMove={onMove}
              onDelete={onDelete}
              onRetry={onRetry}
              onCopyKeyword={onCopyKeyword}
              onDeleteKeyword={onDeleteKeyword}
              onOpenImage={onOpenImage}
              canvasScale={zoom}
            />
          ))}
        </div>
      </div>
    </>
  )
}



