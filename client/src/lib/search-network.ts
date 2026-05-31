import type { SearchKnowledgeNetwork, SearchNetworkEdge, SearchNetworkNode } from "../types/knowledge-network"
import type { KnowledgeSearchResult } from "../types/retrieval"

export function buildSearchKnowledgeNetwork(results: KnowledgeSearchResult[], query: string): SearchKnowledgeNetwork {
  const trimmedQuery = query.trim()
  if (!trimmedQuery || results.length === 0) {
    return { query: trimmedQuery, nodes: [], edges: [] }
  }

  const queryId = `query:${normalizeToken(trimmedQuery) || "search"}`
  const weeks = unique(results.map((result) => result.card?.weekKey).filter((value): value is string => Boolean(value)))
  const nodes: SearchNetworkNode[] = [
    {
      id: queryId,
      type: "query",
      label: trimmedQuery,
      count: results.length,
      weeks,
    },
  ]
  const edges: SearchNetworkEdge[] = []
  const keywordGroups = new Map<string, { label: string; results: Map<string, KnowledgeSearchResult>; weeks: Set<string>; matchedQuery: boolean }>()
  const queryTokens = queryTokenSet(trimmedQuery)

  for (const result of results) {
    const itemNodeId = itemNodeIdFor(result)
    nodes.push({
      id: itemNodeId,
      type: "item",
      label: result.knowledgeItem.title || result.knowledgeItem.summary || "知识条目",
      count: result.knowledgeItem.keywords.length,
      weeks: result.card?.weekKey ? [result.card.weekKey] : [],
      card: result.card,
      knowledgeItem: result.knowledgeItem,
      result,
      score: result.score,
    })
    edges.push({
      id: `${queryId}->${itemNodeId}`,
      source: queryId,
      target: itemNodeId,
      label: "match",
    })

    for (const keyword of result.knowledgeItem.keywords) {
      const normalized = normalizeToken(keyword)
      if (!normalized) continue
      const group =
        keywordGroups.get(normalized) ??
        {
          label: keyword,
          results: new Map<string, KnowledgeSearchResult>(),
          weeks: new Set<string>(),
          matchedQuery: queryTokens.has(normalized) || [...queryTokens].some((token) => token.includes(normalized) || normalized.includes(token)),
        }
      group.results.set(result.knowledgeItem.id, result)
      if (result.card?.weekKey) {
        group.weeks.add(result.card.weekKey)
      }
      keywordGroups.set(normalized, group)
    }
  }

  for (const [normalized, group] of [...keywordGroups.entries()].sort((left, right) => right[1].results.size - left[1].results.size || left[1].label.localeCompare(right[1].label))) {
    if (group.results.size < 2 && !group.matchedQuery) continue
    const keywordNodeId = `keyword:${normalized}`
    nodes.push({
      id: keywordNodeId,
      type: "keyword",
      label: group.label,
      count: group.results.size,
      weeks: [...group.weeks].sort(),
    })
    for (const result of group.results.values()) {
      const itemNodeId = itemNodeIdFor(result)
      edges.push({
        id: `${keywordNodeId}->${itemNodeId}`,
        source: keywordNodeId,
        target: itemNodeId,
        label: group.label,
      })
    }
  }

  return { query: trimmedQuery, nodes, edges }
}

function itemNodeIdFor(result: KnowledgeSearchResult) {
  return `item:${result.knowledgeItem.id}`
}

function queryTokenSet(query: string) {
  const tokens = query
    .split(/[\s,，。.;；:：|/\\()[\]{}"'“”‘’!?！？]+/u)
    .map(normalizeToken)
    .filter(Boolean)
  const full = normalizeToken(query)
  if (full) tokens.push(full)
  return new Set(tokens)
}

function normalizeToken(value: string) {
  return value
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/[^\p{Letter}\p{Number}]+/gu, "")
}

function unique(values: string[]) {
  return [...new Set(values)].sort()
}
