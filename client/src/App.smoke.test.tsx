import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import App from "./App"

const now = "2026-05-31T00:00:00.000Z"

const demoCard = {
  id: "card-1",
  weekKey: "2026-W22",
  type: "text",
  textContent: "跨 agent 接力闭环",
  imageUrl: null,
  sourceUrl: null,
  sourceTitle: null,
  sourceDescription: null,
  summary: "工作状态恢复入口",
  keywords: ["agent", "handoff"],
  x: 120,
  y: 120,
  width: 280,
  rotation: 0,
  styleSeed: "smoke",
  aiStatus: "done",
  aiError: null,
  createdAt: now,
  updatedAt: now,
}

const searchResult = {
  knowledgeItem: {
    id: "item-1",
    sourceItemId: "source-1",
    cardId: "card-1",
    title: "Agent Handoff",
    summary: "恢复当前任务状态",
    content: "resume_work 可以恢复当前目标、下一步和关键决策。",
    keywords: ["agent", "handoff"],
    source: "second_brain",
    sourceRef: "source:source-1",
    knowledgeType: "fragment",
    status: "active",
    createdAt: now,
    updatedAt: now,
  },
  card: demoCard,
  matchedFields: ["summary"],
  score: 1,
  excerpt: "恢复当前任务状态",
  reason: "匹配摘要",
  source: "second_brain",
}

const reviewWorkbench = {
  proposals: [
    {
      id: "proposal-1",
      taskSessionId: null,
      targetStore: "semantic_knowledge",
      type: "lesson",
      title: "记录有意义阶段",
      body: "阶段完成后写入 note。",
      structuredPayload: {},
      scope: "workspace",
      evidenceRefs: ["source:source-1"],
      confidence: 0.8,
      reviewNote: "",
      status: "pending",
      sourceItemId: null,
      knowledgeItemId: null,
      pageId: null,
      decisionRef: "decision:proposal-1",
      createdAt: now,
      resolvedAt: null,
    },
  ],
  profileFacts: [],
  conflicts: [],
  rules: [],
  procedures: [],
  pages: [],
  sources: [],
  counts: { pendingProposals: 1, profileFacts: 0, openConflicts: 0 },
}

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }))
}

describe("App smoke", () => {
  beforeEach(() => {
    Element.prototype.setPointerCapture = vi.fn()
    Element.prototype.releasePointerCapture = vi.fn()
    Element.prototype.hasPointerCapture = vi.fn(() => false)
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes("/api/weeks/")) return jsonResponse([demoCard])
        if (url.includes("/api/reflections")) return jsonResponse([])
        if (url.includes("/api/knowledge/search")) return jsonResponse([searchResult])
        if (url.includes("/api/review/workbench")) return jsonResponse(reviewWorkbench)
        if (url.includes("/api/knowledge/export")) return jsonResponse({ exportPath: "export.zip", files: [] })
        return Promise.resolve(new Response("{}", { status: 404, statusText: "Not Found" }))
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("loads the board, opens search results, and renders the review workbench", async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText("跨 agent 接力闭环")).toBeInTheDocument()

    await user.type(screen.getByLabelText("搜索知识"), "handoff")
    await user.click(screen.getByRole("button", { name: "搜索" }))

    expect(await screen.findByText("Agent Handoff")).toBeInTheDocument()
    expect(screen.getAllByText("恢复当前任务状态").length).toBeGreaterThan(0)

    await user.click(screen.getByTitle("记忆审查台"))

    expect(await screen.findByRole("heading", { name: "记忆审查台" })).toBeInTheDocument()
    expect(screen.getByDisplayValue("记录有意义阶段")).toBeInTheDocument()

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/api/review/workbench"))
    })
  })
})
