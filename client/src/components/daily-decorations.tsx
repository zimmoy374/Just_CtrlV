import type { CSSProperties } from "react"
import type { LucideIcon } from "lucide-react"
import { BookOpen, Coffee, Flower2, Glasses, Headphones, LampDesk, NotebookPen, PenLine, Plane } from "lucide-react"

const ICONS: LucideIcon[] = [BookOpen, Coffee, Flower2, Glasses, Headphones, LampDesk, NotebookPen, PenLine, Plane]

export function DailyDecorations({ dayKey }: { dayKey: string }) {
  const seed = hashDay(dayKey)
  const imageCorner = seed % 4
  const used = new Set<number>()

  return (
    <div className="daily-decorations" aria-hidden="true">
      {[0, 1, 2, 3].map((corner) => {
        if (corner === imageCorner) {
          return (
            <div className={`corner-doodle corner-${corner} is-reference`} key={corner}>
              <img src="/doodles/notebook-mug.png" alt="" />
            </div>
          )
        }

        let iconIndex = (seed + corner * 5) % ICONS.length
        while (used.has(iconIndex)) iconIndex = (iconIndex + 1) % ICONS.length
        used.add(iconIndex)
        const Icon = ICONS[iconIndex]
        const rotation = ((seed >> (corner * 3)) % 19) - 9
        const scale = 0.88 + ((seed + corner * 11) % 18) / 100
        return (
          <div
            className={`corner-doodle corner-${corner}`}
            key={corner}
            style={{ "--doodle-rotation": `${rotation}deg`, "--doodle-scale": scale } as CSSProperties}
          >
            <Icon />
          </div>
        )
      })}
    </div>
  )
}

function hashDay(value: string) {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}
