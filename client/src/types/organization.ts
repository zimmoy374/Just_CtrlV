export type Reflection = {
  id: string
  triggerKey: string
  title: string
  reason: string
  question: string
  relatedKnowledgeItemIds: string[]
  status: "pending" | "accepted" | "dismissed"
  createdAt: string
  resolvedAt?: string | null
}



