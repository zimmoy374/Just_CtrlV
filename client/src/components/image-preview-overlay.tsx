import { useRef } from "react"
import type { PointerEvent as ReactPointerEvent, WheelEvent as ReactWheelEvent } from "react"

import { resolveAssetUrl } from "../lib/api"
import type { InspirationCard } from "../types"

export type ImagePreviewState = {
  card: InspirationCard
  scale: number
  x: number
  y: number
}

type ImagePreviewOverlayProps = {
  preview: ImagePreviewState
  onChange: (preview: ImagePreviewState) => void
  onClose: () => void
}

export function ImagePreviewOverlay({ preview, onChange, onClose }: ImagePreviewOverlayProps) {
  const dragStartRef = useRef<{ clientX: number; clientY: number; x: number; y: number } | null>(null)

  const handleWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    event.preventDefault()
    const nextScale = Math.min(2.4, Math.max(0.55, preview.scale - event.deltaY * 0.0012))
    onChange({ ...preview, scale: Number(nextScale.toFixed(2)) })
  }

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    dragStartRef.current = {
      clientX: event.clientX,
      clientY: event.clientY,
      x: preview.x,
      y: preview.y,
    }
  }

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const start = dragStartRef.current
    if (!start) return
    onChange({
      ...preview,
      x: start.x + event.clientX - start.clientX,
      y: start.y + event.clientY - start.clientY,
    })
  }

  const handlePointerUp = () => {
    dragStartRef.current = null
  }

  return (
    <div className="image-preview-backdrop" onClick={onClose}>
      <div
        className="image-preview-stage"
        onClick={(event) => event.stopPropagation()}
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <img
          src={resolveAssetUrl(preview.card.imageUrl)}
          alt={preview.card.summary || "放大的灵感截图"}
          draggable={false}
          style={{
            transform: `translate(${preview.x}px, ${preview.y}px) scale(${preview.scale})`,
          }}
        />
      </div>
    </div>
  )
}
