export type CardType = "image" | "link" | "text"
export type AiStatus = "pending" | "generating" | "done" | "failed"

export type CaptureCard = {
  id: string
  weekKey: string
  type: CardType
  textContent?: string | null
  imageUrl?: string | null
  sourceUrl?: string | null
  sourceTitle?: string | null
  sourceDescription?: string | null
  summary?: string | null
  keywords: string[]
  x: number
  y: number
  width: number
  rotation: number
  styleSeed: string
  aiStatus: AiStatus
  aiError?: string | null
  createdAt: string
  updatedAt: string
}


