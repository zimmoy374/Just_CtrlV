export type ContextPack = {
  query: string
  protocolReminder: string[]
  relatedPages: unknown[]
  relatedItems: unknown[]
  sourceExcerpts: unknown[]
  budget: {
    maxPages: number
    maxItems: number
    maxSourceExcerpts: number
    maxChars: number
    usedChars: number
    truncated: boolean
  }
  citationRefs: unknown[]
}



