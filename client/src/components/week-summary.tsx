import { NotebookTabs, X } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import type { CaptureCard } from "../types/cards"
import { Button } from "./ui/button"

type WeekSummaryProps = {
  cards: CaptureCard[]
  weekTitle: string
  onSearchKeyword: (keyword: string) => void
}

type KeywordStat = {
  keyword: string
  count: number
}

export function WeekSummary({ cards, weekTitle, onSearchKeyword }: WeekSummaryProps) {
  const [isOpen, setIsOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement | null>(null)

  const stats = useMemo(() => {
    const keywordCounts = new Map<string, number>()
    cards.forEach((card) => {
      card.keywords.forEach((keyword) => {
        keywordCounts.set(keyword, (keywordCounts.get(keyword) ?? 0) + 1)
      })
    })
    const topKeywords: KeywordStat[] = Array.from(keywordCounts, ([keyword, count]) => ({ keyword, count }))
      .sort((a, b) => b.count - a.count || a.keyword.localeCompare(b.keyword, "zh-CN"))
      .slice(0, 5)

    return {
      itemCount: cards.length,
      keywordCount: cards.reduce((total, card) => total + card.keywords.length, 0),
      topKeywords,
    }
  }, [cards])

  useEffect(() => {
    if (!isOpen) return

    const handlePointerDown = (event: PointerEvent) => {
      if (!panelRef.current?.contains(event.target as Node)) {
        setIsOpen(false)
      }
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
    <div className="week-summary-float" ref={panelRef}>
      <button type="button" className={`summary-pin${isOpen ? " is-active" : ""}`} title="周总结" aria-expanded={isOpen} onClick={() => setIsOpen((current) => !current)}>
        <NotebookTabs size={19} />
      </button>

      {isOpen ? (
        <section className="week-summary-panel" aria-label="周总结">
          <div className="summary-panel-head">
            <div>
              <span>周总结</span>
              <h2>{weekTitle}</h2>
            </div>
            <Button type="button" variant="ghost" size="icon" title="关闭周总结" onClick={() => setIsOpen(false)}>
              <X size={15} />
            </Button>
          </div>

          <div className="summary-stats">
            <div>
              <span>本周条目</span>
              <strong>{stats.itemCount}</strong>
            </div>
            <div>
              <span>关键词数</span>
              <strong>{stats.keywordCount}</strong>
            </div>
          </div>

          <div className="summary-terms">
            <span className="summary-label">本周高频关键词</span>
            {stats.topKeywords.length > 0 ? (
              stats.topKeywords.map((item, index) => (
                <button type="button" key={item.keyword} onClick={() => onSearchKeyword(item.keyword)}>
                  <em>{index + 1}</em>
                  <span>{item.keyword}</span>
                  <strong>{item.count} 次</strong>
                </button>
              ))
            ) : (
              <p>还没有可统计的关键词</p>
            )}
          </div>
        </section>
      ) : null}
    </div>
  )
}


