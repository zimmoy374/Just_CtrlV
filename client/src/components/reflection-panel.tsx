import { Check, Sparkles, X } from "lucide-react"

import type { Reflection } from "../types/organization"
import { Button } from "./ui/button"

type ReflectionPanelProps = {
  reflections: Reflection[]
  onAccept: (id: string) => void
  onDismiss: (id: string) => void
}

export function ReflectionPanel({ reflections, onAccept, onDismiss }: ReflectionPanelProps) {
  if (reflections.length === 0) return null

  return (
    <aside className="reflection-panel" aria-label="待整理建议">
      <div className="reflection-head">
        <Sparkles size={17} />
        <span>{reflections.length} 条待整理</span>
      </div>
      {reflections.slice(0, 3).map((reflection) => (
        <article key={reflection.id}>
          <strong>{reflection.title}</strong>
          <p>{reflection.question || reflection.reason}</p>
          <div>
            <Button type="button" variant="secondary" size="sm" onClick={() => onDismiss(reflection.id)}>
              <X size={14} />
              忽略
            </Button>
            <Button type="button" variant="primary" size="sm" onClick={() => onAccept(reflection.id)}>
              <Check size={14} />
              接受
            </Button>
          </div>
        </article>
      ))}
    </aside>
  )
}


