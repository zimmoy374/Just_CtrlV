import { useEffect, useMemo, useState } from "react"
import { ChevronLeft, ChevronRight, X } from "lucide-react"

import { Button } from "./ui/button"

type DayCalendarProps = {
  selectedDay: string
  todayKey: string
  availableDays: string[]
  onSelect: (dayKey: string) => void
  onClose: () => void
}

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

export function DayCalendar({ selectedDay, todayKey, availableDays, onSelect, onClose }: DayCalendarProps) {
  const [visibleMonth, setVisibleMonth] = useState(() => startOfMonth(parseDay(selectedDay)))
  const available = useMemo(() => new Set(availableDays), [availableDays])
  const today = parseDay(todayKey)
  const cells = useMemo(() => buildMonthCells(visibleMonth), [visibleMonth])
  const canMoveForward = monthKey(visibleMonth) < monthKey(startOfMonth(today))

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [onClose])

  return (
    <div className="calendar-backdrop" onPointerDown={onClose}>
      <section className="calendar-dialog" role="dialog" aria-modal="true" aria-label="选择日期" onPointerDown={(event) => event.stopPropagation()}>
        <div className="calendar-head">
          <Button type="button" variant="ghost" size="icon" title="上个月" onClick={() => setVisibleMonth(addMonths(visibleMonth, -1))}>
            <ChevronLeft size={17} />
          </Button>
          <strong>{visibleMonth.getFullYear()} 年 {visibleMonth.getMonth() + 1} 月</strong>
          <Button type="button" variant="ghost" size="icon" title="下个月" disabled={!canMoveForward} onClick={() => setVisibleMonth(addMonths(visibleMonth, 1))}>
            <ChevronRight size={17} />
          </Button>
          <Button type="button" className="calendar-close" variant="ghost" size="icon" title="关闭日历" onClick={onClose}>
            <X size={16} />
          </Button>
        </div>
        <div className="calendar-weekdays" aria-hidden="true">
          {WEEKDAYS.map((day) => <span key={day}>{day}</span>)}
        </div>
        <div className="calendar-grid">
          {cells.map((cell, index) => {
            if (!cell) return <span className="calendar-blank" key={`blank-${index}`} />
            const key = localDayKey(cell)
            const hasContent = available.has(key)
            const isToday = key === todayKey
            const isSelected = key === selectedDay
            const isFuture = key > todayKey
            const isEnabled = !isFuture && (isToday || hasContent)
            return (
              <button
                type="button"
                className={`calendar-day${hasContent ? " has-content" : ""}${isToday ? " is-today" : ""}${isSelected ? " is-selected" : ""}`}
                key={key}
                disabled={!isEnabled}
                aria-label={key}
                onClick={() => onSelect(key)}
              >
                <span>{cell.getDate()}</span>
                {hasContent ? <i /> : null}
              </button>
            )
          })}
        </div>
      </section>
    </div>
  )
}

function parseDay(value: string) {
  const [year, month, day] = value.split("-").map(Number)
  return new Date(year, month - 1, day)
}

function startOfMonth(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), 1)
}

function addMonths(value: Date, amount: number) {
  return new Date(value.getFullYear(), value.getMonth() + amount, 1)
}

function monthKey(value: Date) {
  return value.getFullYear() * 12 + value.getMonth()
}

function buildMonthCells(month: Date) {
  const leading = (month.getDay() + 6) % 7
  const dayCount = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const cells: Array<Date | null> = Array.from({ length: leading }, () => null)
  for (let day = 1; day <= dayCount; day += 1) cells.push(new Date(month.getFullYear(), month.getMonth(), day))
  while (cells.length % 7 !== 0) cells.push(null)
  return cells
}

function localDayKey(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, "0")
  const day = String(value.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}
