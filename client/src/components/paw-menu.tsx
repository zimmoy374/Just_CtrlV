import { useEffect, useRef, useState } from "react"
import { CalendarDays, CalendarHeart, PawPrint } from "lucide-react"

import { Button } from "./ui/button"

type PawMenuProps = {
  selectedDay: string
  todayKey: string
  onOpenCalendar: () => void
  onToday: () => void
}

export function PawMenu({ selectedDay, todayKey, onOpenCalendar, onToday }: PawMenuProps) {
  const [isOpen, setIsOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!isOpen) return
    const handlePointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setIsOpen(false)
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false)
    }
    window.addEventListener("pointerdown", handlePointerDown)
    window.addEventListener("keydown", handleKeyDown)
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown)
      window.removeEventListener("keydown", handleKeyDown)
    }
  }, [isOpen])

  return (
    <div className={`paw-menu${isOpen ? " is-open" : ""}`} ref={menuRef}>
      <button
        type="button"
        className="paw-trigger"
        title={selectedDay}
        aria-label="打开日期工具"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className="paw-arm">
          <PawPrint size={27} strokeWidth={1.55} />
        </span>
      </button>
      <div className="paw-actions" aria-hidden={!isOpen}>
        <Button
          type="button"
          variant="secondary"
          size="icon"
          title="打开日历"
          onClick={() => {
            setIsOpen(false)
            onOpenCalendar()
          }}
        >
          <CalendarDays size={18} />
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="icon"
          title="回到今天"
          disabled={selectedDay === todayKey}
          onClick={() => {
            setIsOpen(false)
            onToday()
          }}
        >
          <CalendarHeart size={18} />
        </Button>
      </div>
    </div>
  )
}
