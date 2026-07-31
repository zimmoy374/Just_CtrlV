import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import App from "./App"
import { parseResponse } from "./lib/api/client"

const todayKey = localDayKey(new Date())
const now = `${todayKey}T00:00:00.000Z`
const demoCard = {
  id: "card-1",
  dayKey: todayKey,
  type: "text",
  textContent: "粘贴进白板的内容",
  imageUrl: null,
  sourceUrl: null,
  sourceTitle: null,
  sourceDescription: null,
  summary: "自动生成的摘要",
  keywords: ["白板", "摘要"],
  x: 0.12,
  y: 0.12,
  width: 280,
  rotation: 0,
  styleSeed: "smoke",
  aiStatus: "done",
  aiError: null,
  createdAt: now,
  updatedAt: now,
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
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith("/api/days") && !init?.method) return jsonResponse([todayKey])
        if (url.endsWith(`/api/days/${todayKey}/cards`) && !init?.method) return jsonResponse([demoCard])
        if (url.endsWith("/api/cards/text") && init?.method === "POST") {
          return jsonResponse({ ...demoCard, id: "card-2", textContent: "新的粘贴内容", summary: "新的内容摘要", x: 0.38, y: 0.3 })
        }
        return Promise.resolve(new Response("{}", { status: 404, statusText: "Not Found" }))
      }),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("loads today's desk and accepts pasted text without overlapping the existing card", async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText("自动生成的摘要")).toBeInTheDocument()
    expect(screen.queryByText("粘贴进白板的内容")).not.toBeInTheDocument()

    await user.click(screen.getByTitle("展开原文"))
    expect(screen.getByText("粘贴进白板的内容")).toBeInTheDocument()

    fireEvent.paste(window, {
      clipboardData: {
        items: [],
        getData: (type: string) => (type === "text/plain" ? "新的粘贴内容" : ""),
      },
    })

    expect(await screen.findByText("新的内容摘要")).toBeInTheDocument()
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/api/cards/text"), expect.objectContaining({ method: "POST" })))
    const createCall = vi.mocked(fetch).mock.calls.find(([url, init]) => String(url).endsWith("/api/cards/text") && init?.method === "POST")
    const createPayload = JSON.parse(String(createCall?.[1]?.body)) as { dayKey: string; x: number; y: number }
    expect(createPayload.dayKey).toBe(todayKey)
    expect(createPayload.x).toBeGreaterThanOrEqual(0)
    expect(createPayload.x).toBeLessThanOrEqual(1)
    expect(createPayload.y).toBeGreaterThanOrEqual(0)
    expect(createPayload.y).toBeLessThanOrEqual(1)
    expect(createPayload).not.toMatchObject({ x: demoCard.x, y: demoCard.y })
  })

  it("opens the calendar from the paw and disables empty historical dates", async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText("自动生成的摘要")

    await user.click(screen.getByRole("button", { name: "打开日期工具" }))
    await user.click(screen.getByTitle("打开日历"))

    expect(screen.getByRole("dialog", { name: "选择日期" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: todayKey })).toBeEnabled()

    const historical = yesterdayKey()
    if (historical.slice(0, 7) !== todayKey.slice(0, 7)) await user.click(screen.getByTitle("上个月"))
    expect(screen.getByRole("button", { name: historical })).toBeDisabled()
  })

  it("translates gateway failures into a recoverable local-service message", async () => {
    await expect(parseResponse(new Response("Bad Gateway", { status: 502 }))).rejects.toThrow("后台服务未连接，正在等待恢复")
  })
})

function localDayKey(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, "0")
  const day = String(value.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function yesterdayKey() {
  const yesterday = new Date()
  yesterday.setDate(yesterday.getDate() - 1)
  return localDayKey(yesterday)
}
