await loadAnimator()

const API_BASE = String(window.CTRLV_API_BASE || "").replace(/\/$/, "")
const INTERACTIVE = ".capture-card,.composer,.paw-menu,.calendar-dialog,button,textarea,input,a"
const WORLD_WIDTH = 6000
const WORLD_HEIGHT = 4000
const MIN_ZOOM = 0.25
const MAX_ZOOM = 2.5
const REFERENCE_CARD_WIDTH = 280
const MIN_CARD_SCREEN_WIDTH = 260
const MAX_CARD_SCREEN_WIDTH = 340
const CARD_VIEWPORT_RATIO = 0.17
const COMPACT_CARD_IMAGE_HEIGHT = 220
const animator = window.gsap
const state = {
  today: dayKey(new Date()),
  day: dayKey(new Date()),
  days: [],
  cards: [],
  pointer: null,
  poll: null,
  zoom: 1,
  panX: 0,
  panY: 0,
  panGesture: null,
  spacePressed: false,
  suppressDoubleClickUntil: 0,
  sourceHideTimer: null,
  locateTimer: null,
  memorySeen: new Set(),
  memoryBusy: false,
  memoryCard: null,
  memoryTimeline: null,
}

const app = document.querySelector("#app")
app.innerHTML = `
  <div class="app-shell">
    <time class="day-stamp"></time>
    <div class="paw-menu">
      <button class="paw-trigger" title="日期工具" aria-label="打开日期工具" aria-expanded="false">
        <span class="paw-arm"><span class="paw-icon"><i></i><i></i><i></i><i></i><b></b></span></span>
      </button>
      <div class="paw-actions" aria-hidden="true">
        <button class="button secondary icon open-calendar" title="打开日历" aria-label="打开日历"><span class="calendar-icon" aria-hidden="true"><i></i></span></button>
        <button class="button secondary icon today-button" title="回到今天" aria-label="回到今天">⌂</button>
        <button class="button secondary icon camera-fit" title="显示全部内容" aria-label="显示全部内容">⊙</button>
        <button class="button secondary icon open-settings" title="全局剪刀设置" aria-label="全局剪刀设置">⚙</button>
      </div>
    </div>
    <main class="board-wrap">
      <div class="daily-desk"></div>
      <div class="notice error-banner" hidden></div>
      <div class="notice toast" hidden></div>
    </main>
    <div class="source-layer" aria-live="polite"></div>
    <button class="memory-box" type="button" aria-label="摇一摇，捞起一张旧碎片">
      <img class="memory-paper-plane" src="./img/memory-paper-plane.png?v=20260730" alt="" aria-hidden="true">
      <span class="memory-box-hint" aria-hidden="true">摇一摇，捞起一张旧碎片</span>
    </button>
    <div class="memory-layer" aria-live="polite"></div>
  </div>`

const board = document.querySelector(".daily-desk")
const boardWrap = document.querySelector(".board-wrap")
const sourceLayer = document.querySelector(".source-layer")
const memoryBox = document.querySelector(".memory-box")
const memoryLayer = document.querySelector(".memory-layer")
const pawMenu = document.querySelector(".paw-menu")
const pawTrigger = document.querySelector(".paw-trigger")

memoryBox.addEventListener("click", drawMemory)
pawTrigger.addEventListener("click", () => togglePaw(!pawMenu.classList.contains("open")))
document.querySelector(".open-calendar").addEventListener("click", () => { togglePaw(false); openCalendar() })
document.querySelector(".today-button").addEventListener("click", () => { togglePaw(false); selectDay(state.today) })
document.querySelector(".camera-fit").addEventListener("click", () => { togglePaw(false); fitCards() })
document.querySelector(".open-settings").addEventListener("click", () => { togglePaw(false); openSettings() })
document.addEventListener("pointerdown", (event) => {
  if (!pawMenu.contains(event.target)) togglePaw(false)
})
document.addEventListener("keydown", (event) => {
  if (event.code === "Space" && !event.target.closest?.("textarea,input,[contenteditable='true']")) {
    state.spacePressed = true
    boardWrap.classList.add("pan-ready")
    event.preventDefault()
  }
  if (event.key === "Escape") {
    if (state.memoryCard) {
      dismissMemoryCard()
      return
    }
    togglePaw(false)
    closeOverlay()
  }
})
document.addEventListener("keyup", (event) => {
  if (event.code === "Space") {
    state.spacePressed = false
    boardWrap.classList.remove("pan-ready")
  }
})

boardWrap.addEventListener("pointerdown", startCameraPan)
boardWrap.addEventListener("pointermove", moveCameraPan)
boardWrap.addEventListener("pointerup", finishCameraPan)
boardWrap.addEventListener("pointercancel", finishCameraPan)
boardWrap.addEventListener("dblclick", (event) => {
  if (performance.now() < state.suppressDoubleClickUntil) return
  if (!event.target.closest(INTERACTIVE)) openComposer(clientPoint(event.clientX, event.clientY))
})
boardWrap.addEventListener("wheel", zoomBoard, { passive: false })
window.addEventListener("paste", handlePaste)
window.addEventListener("resize", () => {
  restoreCamera(state.day)
  fitKeywordRows()
  keepOpenComposerInViewport()
})

restoreCamera(state.day)
await refresh()
syncActiveDay()

async function refresh() {
  try {
    const [loadedCards, days] = await Promise.all([request(`/api/days/${encodeURIComponent(state.day)}/cards`), request("/api/days")])
    const cards = await migrateLegacyPositions(loadedCards)
    const current = new Map(state.cards.map((card) => [card.id, card]))
    state.cards = cards.map((card) => {
      const existing = current.get(card.id)
      if (!existing) return card
      Object.assign(existing, card)
      return existing
    })
    state.days = days
    render()
    setError("")
    schedulePoll()
  } catch (error) {
    setError(error.message || "加载失败")
  }
}

function render() {
  const date = parseDay(state.day)
  const stamp = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "short" }).format(date)
  const time = document.querySelector(".day-stamp")
  time.dateTime = state.day
  time.textContent = stamp
  document.querySelector(".today-button").disabled = state.day === state.today
  renderCards()
}

function renderCards() {
  const existing = new Map(
    Array.from(board.querySelectorAll(".capture-card[data-card-id]"), (node) => [node.dataset.cardId, node]),
  )
  for (const card of state.cards) {
    const current = existing.get(card.id)
    const renderKey = cardRenderKey(card)
    if (current?.dataset.renderKey === renderKey) {
      current.style.left = `${card.x}px`
      current.style.top = `${card.y}px`
      current.style.width = `${card.width}px`
      existing.delete(card.id)
      continue
    }

    const next = createCard(card)
    next.dataset.cardId = card.id
    next.dataset.renderKey = renderKey
    if (current) {
      const previousImage = current.querySelector(".image-frame img")
      const nextImage = next.querySelector(".image-frame img")
      if (previousImage && nextImage && previousImage.src === nextImage.src) nextImage.replaceWith(previousImage)
      current.replaceWith(next)
    } else board.append(next)
    existing.delete(card.id)
  }
  for (const stale of existing.values()) stale.remove()
  requestAnimationFrame(fitKeywordRows)
}

function createCard(card) {
  const article = document.createElement("article")
  article.className = `capture-card ${card.type}-card${card.isCutout ? " cutout-piece" : ""}`
  article.tabIndex = 0
  article.style.left = `${card.x}px`
  article.style.top = `${card.y}px`
  article.style.width = `${card.width}px`
  const inner = document.createElement("div")
  inner.className = "card-inner"
  article.append(inner)

  const actions = element("div", "card-actions")
  if (card.type === "text" && card.summary && card.textContent) {
    const expand = iconButton("⌄", "展开原文")
    expand.addEventListener("click", () => toggleRaw(card, inner, expand))
    actions.append(expand)
  }
  if (!card.isCutout && card.aiStatus === "failed") {
    const retry = iconButton("↻", "重试智能整理")
    retry.addEventListener("click", () => retryCard(card))
    actions.append(retry)
  }
  const remove = iconButton("×", "删除卡片")
  remove.addEventListener("click", () => removeCard(card))
  actions.append(remove)
  inner.append(actions)

  if (card.type === "image") inner.append(imageContent(card))
  else if (card.type === "link") inner.append(linkContent(card))
  else inner.append(textContent(card))
  if (!card.isCutout) {
    if (card.type !== "text" && card.summary) inner.append(textElement("p", "card-summary", card.summary))
    inner.append(keywordContent(card))
  }
  attachDrag(article, card)
  if (card.isCutout) attachSourceHover(article, card)
  return article
}

function textContent(card) {
  const wrapper = document.createElement("div")
  if (card.summary) wrapper.append(textElement("p", "card-summary summary-primary", card.summary))
  if (!card.summary) wrapper.append(textElement("p", "text-content", card.textContent || ""))
  return wrapper
}

function toggleRaw(card, inner, button) {
  const existing = inner.querySelector(".raw-content")
  if (existing) {
    existing.remove()
    button.textContent = "⌄"
    button.title = "展开原文"
    return
  }
  const raw = element("div", "raw-content expanded")
  raw.append(textElement("span", "", "原文"), textElement("p", "text-content", card.textContent || ""))
  inner.insertBefore(raw, inner.querySelector(".keyword-area"))
  button.textContent = "⌃"
  button.title = "收起原文"
}

function imageContent(card) {
  const frame = element("div", "image-frame")
  const image = document.createElement("img")
  image.src = assetUrl(card.imageUrl)
  image.alt = card.isCutout ? "裁剪素材" : card.summary || "粘贴的图片"
  image.draggable = false
  image.addEventListener("dblclick", (event) => { event.stopPropagation(); openPreview(card) })
  frame.append(image)
  return frame
}

function sourceInfo(card) {
  let label = card.sourceTitle || card.sourceApp || "手动粘贴"
  if (card.sourceUrl) {
    try { label = new URL(card.sourceUrl).host || label } catch {}
  } else if (card.sourceFile) {
    label = card.sourceFile.split(/[\\/]/).at(-1) || label
  }
  const details = [
    card.sourceTitle !== label ? card.sourceTitle : "",
    card.sourceApp,
    card.sourceUrl,
    card.sourceFile,
    card.sourceCapturedAt ? `裁剪于 ${new Date(card.sourceCapturedAt).toLocaleString("zh-CN")}` : "",
  ].filter(Boolean)
  return { label, details }
}

function attachSourceHover(article, card) {
  article.addEventListener("pointerenter", () => showSourceFloat(article, card))
  article.addEventListener("pointerleave", scheduleSourceHide)
  article.addEventListener("focusin", () => showSourceFloat(article, card))
  article.addEventListener("focusout", scheduleSourceHide)
}

function showSourceFloat(article, card) {
  clearTimeout(state.sourceHideTimer)
  clearTimeout(state.locateTimer)
  const { label, details } = sourceInfo(card)
  const float = element("div", "source-float")
  float.dataset.cardId = card.id
  const chip = card.sourceUrl ? document.createElement("a") : document.createElement("span")
  chip.className = "source-chip"
  chip.append(element("i", "source-dot"), textElement("span", "", label))
  if (card.sourceUrl) {
    chip.href = card.sourceUrl
    chip.target = "_blank"
    chip.rel = "noreferrer"
  }
  if (details.length) {
    const detail = element("div", "source-popover")
    detail.append(...details.map((value, index) => textElement(index === 0 ? "strong" : "span", "", value)))
    float.append(chip, detail)
  } else {
    float.append(chip)
  }
  sourceLayer.replaceChildren(float)
  placeSourceFloat(float, article)
}

function scheduleSourceHide() {
  clearTimeout(state.sourceHideTimer)
  state.sourceHideTimer = setTimeout(hideSourceFloat, 180)
}

function hideSourceFloat() {
  clearTimeout(state.sourceHideTimer)
  sourceLayer.replaceChildren()
}

sourceLayer.addEventListener("pointerenter", () => clearTimeout(state.sourceHideTimer))
sourceLayer.addEventListener("pointerleave", scheduleSourceHide)

function placeSourceFloat(float, article) {
  const cardRect = article.getBoundingClientRect()
  const labelRect = float.getBoundingClientRect()
  const gap = 10
  const candidates = [
    { side: "bottom", x: cardRect.left + (cardRect.width - labelRect.width) / 2, y: cardRect.bottom + gap },
    { side: "top", x: cardRect.left + (cardRect.width - labelRect.width) / 2, y: cardRect.top - labelRect.height - gap },
    { side: "right", x: cardRect.right + gap, y: cardRect.top + (cardRect.height - labelRect.height) / 2 },
    { side: "left", x: cardRect.left - labelRect.width - gap, y: cardRect.top + (cardRect.height - labelRect.height) / 2 },
  ]
  const protectedRects = [
    document.querySelector(".day-stamp").getBoundingClientRect(),
    pawMenu.getBoundingClientRect(),
    ...Array.from(document.querySelectorAll(".capture-card"), (node) => node === article ? null : node.getBoundingClientRect()).filter(Boolean),
  ]
  const viewport = { left: 8, top: 8, right: window.innerWidth - 8, bottom: window.innerHeight - 8 }
  const scored = candidates.map((candidate, preference) => {
    const rectangle = {
      left: candidate.x,
      top: candidate.y,
      right: candidate.x + labelRect.width,
      bottom: candidate.y + labelRect.height,
    }
    const overflow = Math.max(0, viewport.left - rectangle.left)
      + Math.max(0, rectangle.right - viewport.right)
      + Math.max(0, viewport.top - rectangle.top)
      + Math.max(0, rectangle.bottom - viewport.bottom)
    const collisions = protectedRects.reduce((total, other) => total + rectangleOverlap(rectangle, other), 0)
    return { ...candidate, score: overflow * 10000 + collisions + preference }
  }).sort((left, right) => left.score - right.score)
  const best = scored[0]
  float.dataset.popover = best.y > window.innerHeight * 0.58 ? "up" : "down"
  float.style.left = `${clamp(best.x, viewport.left, viewport.right - labelRect.width)}px`
  float.style.top = `${clamp(best.y, viewport.top, viewport.bottom - labelRect.height)}px`
}

function rectangleOverlap(first, second) {
  const width = Math.max(0, Math.min(first.right, second.right) - Math.max(first.left, second.left))
  const height = Math.max(0, Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top))
  return width * height
}

async function drawMemory() {
  if (state.memoryBusy) return
  state.memoryBusy = true
  try {
    if (state.memoryCard) await dismissMemoryCard()
    const card = await pickMemoryCard()
    if (card?.imageUrl) await preloadImage(assetUrl(card.imageUrl))
    await shakeMemoryBox(Boolean(card))
    if (!card) {
      showMemoryMessage("盒子里还没有旧碎片")
      return
    }
    await presentMemoryCard(card)
  } catch (error) {
    showMemoryMessage("今天盒子有点打不开")
  } finally {
    state.memoryBusy = false
  }
}

async function pickMemoryCard(retry = true) {
  const days = shuffle(state.days.filter((day) => day < state.today && day !== state.day))
  for (const day of days) {
    const cards = await request(`/api/days/${encodeURIComponent(day)}/cards`)
    const available = cards.filter((card) => !state.memorySeen.has(card.id))
    if (!available.length) continue
    const card = available[Math.floor(Math.random() * available.length)]
    state.memorySeen.add(card.id)
    return card
  }
  if (retry && state.memorySeen.size) {
    state.memorySeen.clear()
    return pickMemoryCard(false)
  }
  return null
}

function shakeMemoryBox(dropCrumbs) {
  const illustration = memoryBox.querySelector(".memory-paper-plane")
  if (reducedMotion() || !animator) return wait(80)
  const crumbs = dropCrumbs ? createMemoryCrumbs() : []
  memoryBox.classList.add("busy")
  return new Promise((resolve) => {
    const timeline = animator.timeline({
      defaults: { ease: "power2.inOut" },
      onComplete: () => {
        animator.set(illustration, { clearProps: "transform" })
        crumbs.forEach((crumb) => crumb.remove())
        memoryBox.classList.remove("busy")
        state.memoryTimeline = null
        resolve()
      },
    })
    state.memoryTimeline = timeline
    timeline
      .to(illustration, { y: 3, scale: 0.97, duration: 0.08 })
      .to(illustration, { x: -6, rotation: -2.8, duration: 0.07 })
      .to(illustration, { x: 6, rotation: 2.6, duration: 0.07 })
      .to(illustration, { x: -4, rotation: -1.8, duration: 0.07 })
      .to(illustration, { x: 3, rotation: 1.2, duration: 0.07 })
      .to(illustration, { x: 0, y: 0, rotation: 0, scale: 1, duration: 0.16, ease: "power2.out" })
    if (crumbs.length) {
      timeline.fromTo(
        crumbs,
        { x: 0, y: 0, rotation: 0, autoAlpha: 0, scale: 0.5 },
        {
          x: (_, crumb) => Number(crumb.dataset.x),
          y: (_, crumb) => Number(crumb.dataset.y),
          rotation: (_, crumb) => Number(crumb.dataset.rotation),
          autoAlpha: 0,
          scale: 1,
          duration: 0.48,
          stagger: 0.035,
          ease: "power2.out",
        },
        0.22,
      )
    }
  })
}

function createMemoryCrumbs() {
  const rect = memoryBox.getBoundingClientRect()
  return Array.from({ length: 3 }, (_, index) => {
    const crumb = element("i", `memory-crumb crumb-${index + 1}`)
    crumb.style.left = `${rect.left + rect.width * (0.38 + index * 0.13)}px`
    crumb.style.top = `${rect.top + rect.height * 0.28}px`
    crumb.dataset.x = String(-36 + index * 31)
    crumb.dataset.y = String(-34 - index * 13)
    crumb.dataset.rotation = String(-38 + index * 39)
    memoryLayer.append(crumb)
    return crumb
  })
}

async function presentMemoryCard(card) {
  const shell = element("div", "memory-card-shell")
  const article = createMemoryCard(card)
  shell.append(article)
  shell.addEventListener("pointerdown", (event) => {
    if (event.target === shell && state.memoryCard) dismissMemoryCard()
  })
  memoryLayer.replaceChildren(shell)
  memoryLayer.classList.add("open")

  const boxRect = memoryBox.getBoundingClientRect()
  const offsetX = boxRect.left + boxRect.width / 2 - window.innerWidth / 2
  const offsetY = boxRect.top + boxRect.height / 2 - window.innerHeight / 2
  if (reducedMotion() || !animator) {
    article.style.opacity = "1"
  } else {
    await new Promise((resolve) => {
      const timeline = animator.timeline({
        onComplete: () => {
          state.memoryTimeline = null
          resolve()
        },
      })
      state.memoryTimeline = timeline
      timeline.fromTo(
        article,
        { x: offsetX, y: offsetY, scale: 0.12, rotation: 7, autoAlpha: 0 },
        {
          keyframes: [
            { x: offsetX * 0.55, y: offsetY * 0.46 - 36, scale: 0.58, rotation: -3, autoAlpha: 1, duration: 0.2, ease: "power2.out" },
            { x: 0, y: 0, scale: 1, rotation: 0, duration: 0.36, ease: "back.out(1.18)" },
          ],
        },
      )
    })
  }
  state.memoryCard = { data: card, node: article, shell }
}

function createMemoryCard(card) {
  const article = element("article", "memory-card")
  article.setAttribute("role", "dialog")
  article.setAttribute("aria-label", "随机旧碎片")
  const header = element("header", "memory-card-head")
  const date = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric" }).format(parseDay(card.dayKey))
  header.append(
    textElement("span", "memory-date", date),
    textElement("span", "memory-type", card.isCutout ? "裁剪" : ({ text: "文字", link: "链接", image: "图片" }[card.type] || "碎片")),
  )
  const close = iconButton("×", "收回盒子")
  close.classList.add("memory-close")
  close.addEventListener("click", dismissMemoryCard)
  header.append(close)

  const body = element("div", "memory-card-body")
  if (card.type === "image" && card.imageUrl) {
    const image = document.createElement("img")
    image.className = `memory-image${card.isCutout ? " cutout" : ""}`
    image.src = assetUrl(card.imageUrl)
    image.alt = card.summary || "旧图片碎片"
    image.draggable = false
    body.append(image)
  }
  const title = card.type === "link"
    ? card.sourceTitle || card.sourceUrl
    : card.summary || (card.type === "text" ? truncate(card.textContent, 180) : "")
  if (title) body.append(textElement("p", "memory-summary", title))
  if (card.type === "text" && card.summary && card.textContent) {
    body.append(textElement("p", "memory-excerpt", truncate(card.textContent, 150)))
  }
  if (card.keywords?.length) {
    const keywords = element("div", "memory-keywords")
    keywords.append(...card.keywords.slice(0, 5).map((keyword) => textElement("span", "", keyword)))
    body.append(keywords)
  }
  const source = sourceInfo(card)
  body.append(textElement("p", "memory-source", source.label))

  const actions = element("footer", "memory-actions")
  const visit = textElement("button", "button primary", "回到那天")
  const again = textElement("button", "button secondary", "再摇一次")
  const dismiss = textElement("button", "button secondary", "收回")
  visit.type = again.type = dismiss.type = "button"
  visit.addEventListener("click", () => jumpToMemory(card))
  again.addEventListener("click", drawMemory)
  dismiss.addEventListener("click", dismissMemoryCard)
  actions.append(visit, again, dismiss)
  article.append(header, body, actions)
  return article
}

function dismissMemoryCard() {
  const current = state.memoryCard
  if (!current) return Promise.resolve()
  state.memoryCard = null
  const boxRect = memoryBox.getBoundingClientRect()
  const offsetX = boxRect.left + boxRect.width / 2 - window.innerWidth / 2
  const offsetY = boxRect.top + boxRect.height / 2 - window.innerHeight / 2
  if (reducedMotion() || !animator) {
    memoryLayer.classList.remove("open")
    memoryLayer.replaceChildren()
    return Promise.resolve()
  }
  return new Promise((resolve) => {
    const timeline = animator.timeline({
      onComplete: () => {
        memoryLayer.classList.remove("open")
        memoryLayer.replaceChildren()
        state.memoryTimeline = null
        resolve()
      },
    })
    state.memoryTimeline = timeline
    timeline
      .to(current.node, { x: offsetX * 0.5, y: offsetY * 0.45 - 28, scale: 0.56, rotation: 4, duration: 0.16, ease: "power2.in" })
      .to(current.node, { x: offsetX, y: offsetY, scale: 0.1, rotation: -7, autoAlpha: 0, duration: 0.24, ease: "power2.in" })
  })
}

async function jumpToMemory(card) {
  if (state.memoryBusy) return
  state.memoryBusy = true
  try {
    await dismissMemoryCard()
    await selectDay(card.dayKey)
    await focusCard(card.id)
  } finally {
    state.memoryBusy = false
  }
}

async function focusCard(cardId) {
  const card = state.cards.find((item) => item.id === cardId)
  if (!card) return
  const viewport = boardWrap.getBoundingClientRect()
  const targetZoom = clamp(state.zoom, 0.72, 1.15)
  const targetCenterX = card.x + card.width / 2
  const targetCenterY = card.y + estimatedCardHeight(card) / 2
  const start = { zoom: state.zoom, panX: state.panX, panY: state.panY }
  state.zoom = targetZoom
  state.panX = viewport.width / 2 - targetCenterX * targetZoom
  state.panY = viewport.height / 2 - targetCenterY * targetZoom
  constrainCamera()
  const target = { zoom: state.zoom, panX: state.panX, panY: state.panY }
  Object.assign(state, start)

  if (reducedMotion() || !animator) {
    Object.assign(state, target)
    applyBoardTransform()
  } else {
    const camera = { ...start }
    await new Promise((resolve) => {
      animator.to(camera, {
        ...target,
        duration: 0.52,
        ease: "power3.inOut",
        onUpdate: () => {
          state.zoom = camera.zoom
          state.panX = camera.panX
          state.panY = camera.panY
          applyBoardTransform()
        },
        onComplete: resolve,
      })
    })
  }
  saveCamera()
  await new Promise((resolve) => requestAnimationFrame(resolve))
  const article = board.querySelector(`.capture-card[data-card-id="${cardId}"]`)
  if (article) showLocateHint(article)
}

function showLocateHint(article) {
  clearTimeout(state.locateTimer)
  hideSourceFloat()
  const hint = textElement("div", "locate-hint", "我在这")
  sourceLayer.replaceChildren(hint)
  const cardRect = article.getBoundingClientRect()
  const hintRect = hint.getBoundingClientRect()
  hint.style.left = `${clamp(cardRect.left + (cardRect.width - hintRect.width) / 2, 8, window.innerWidth - hintRect.width - 8)}px`
  hint.style.top = `${Math.max(8, cardRect.top - hintRect.height - 11)}px`
  if (animator && !reducedMotion()) animator.fromTo(hint, { y: 5, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.2, ease: "power2.out" })
  state.locateTimer = setTimeout(() => {
    if (!hint.isConnected) return
    if (animator && !reducedMotion()) {
      animator.to(hint, { y: -3, autoAlpha: 0, duration: 0.22, onComplete: () => hint.remove() })
    } else hint.remove()
  }, 1700)
}

function showMemoryMessage(text) {
  const existing = memoryLayer.querySelector(".memory-message")
  existing?.remove()
  const message = textElement("div", "memory-message", text)
  const rect = memoryBox.getBoundingClientRect()
  message.style.right = `${Math.max(12, window.innerWidth - rect.right)}px`
  message.style.bottom = `${window.innerHeight - rect.top + 8}px`
  memoryLayer.append(message)
  if (animator && !reducedMotion()) animator.fromTo(message, { y: 5, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.18 })
  setTimeout(() => {
    if (!message.isConnected) return
    if (animator && !reducedMotion()) animator.to(message, { autoAlpha: 0, duration: 0.2, onComplete: () => message.remove() })
    else message.remove()
  }, 1800)
}

function preloadImage(url) {
  return new Promise((resolve) => {
    const image = new Image()
    const finish = () => resolve()
    image.onload = finish
    image.onerror = finish
    image.src = url
    setTimeout(finish, 700)
  })
}

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

function shuffle(values) {
  const result = [...values]
  for (let index = result.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(Math.random() * (index + 1))
    ;[result[index], result[swap]] = [result[swap], result[index]]
  }
  return result
}

function truncate(value, length) {
  const text = String(value || "").trim()
  return text.length > length ? `${text.slice(0, length).trim()}…` : text
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

function loadAnimator() {
  if (window.gsap) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const script = document.createElement("script")
    script.src = "./vendor/gsap.min.js?v=3.15.0"
    script.onload = resolve
    script.onerror = () => reject(new Error("动画组件加载失败"))
    document.head.append(script)
  })
}

function linkContent(card) {
  const link = document.createElement("a")
  link.className = "link-preview"
  link.href = card.sourceUrl || "#"
  link.target = "_blank"
  link.rel = "noreferrer"
  link.append(
    textElement("span", "link-preview-icon", "↗"),
    textElement("strong", "", card.sourceTitle || card.sourceUrl || "链接"),
  )
  if (card.sourceDescription) link.append(textElement("span", "", card.sourceDescription))
  link.append(textElement("em", "", "打开链接 ↗"))
  return link
}

function keywordContent(card) {
  const area = element("div", "keyword-area")
  if (!card.keywords.length) {
    const labels = { pending: "待生成", generating: "生成中", done: "已提炼", failed: "待重试" }
    const status = textElement("span", `status-pill ${card.aiStatus}`, labels[card.aiStatus])
    status.title = card.aiError || labels[card.aiStatus]
    area.append(status)
    if (card.aiStatus === "failed" && card.aiError) area.append(textElement("p", "ai-error-text", card.aiError))
    return area
  }
  const row = element("div", "keyword-row")
  for (const keyword of card.keywords) {
    const chip = textElement("button", "keyword-chip", keyword)
    chip.type = "button"
    chip.title = `复制：${keyword}`
    chip.addEventListener("click", () => copyKeyword(keyword))
    row.append(chip)
  }
  const overflow = textElement("span", "keyword-overflow", "")
  overflow.hidden = true
  row.append(overflow)
  const expanded = element("div", "keyword-expanded")
  for (const keyword of card.keywords) {
    const token = element("span", "keyword-token")
    const copy = textElement("button", "keyword-copy", keyword)
    copy.title = "复制关键词"
    copy.addEventListener("click", () => copyKeyword(keyword))
    const remove = textElement("button", "delete-keyword", "×")
    remove.title = "删除关键词"
    remove.addEventListener("click", () => deleteKeyword(card, keyword))
    token.append(copy, remove)
    expanded.append(token)
  }
  area.append(row, expanded)
  return area
}

function fitKeywordRows() {
  for (const row of document.querySelectorAll(".keyword-row")) {
    const chips = Array.from(row.querySelectorAll(".keyword-chip"))
    const overflow = row.querySelector(".keyword-overflow")
    if (!overflow || !row.clientWidth) continue
    for (const chip of chips) chip.hidden = false
    overflow.hidden = true
    let visible = chips.length
    while (row.scrollWidth > row.clientWidth && visible > 0) {
      visible -= 1
      chips[visible].hidden = true
      overflow.textContent = `+${chips.length - visible}`
      overflow.hidden = false
    }
  }
}

function attachDrag(article, card) {
  let start = null
  article.addEventListener("pointerdown", (event) => {
    if (
      event.button !== 0
      || state.spacePressed
      || event.target.closest("button,a")
      || (!card.isCutout && event.target.closest(".image-frame"))
    ) return
    event.preventDefault()
    hideSourceFloat()
    article.setPointerCapture(event.pointerId)
    start = {
      id: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      cardX: card.x,
      cardY: card.y,
      zoom: state.zoom,
      moved: false,
    }
  })
  article.addEventListener("pointermove", (event) => {
    if (start?.id !== event.pointerId) return
    event.preventDefault()
    const deltaX = event.clientX - start.clientX
    const deltaY = event.clientY - start.clientY
    if (!start.moved && Math.hypot(deltaX, deltaY) < 4) return
    if (!start.moved) {
      start.moved = true
      article.classList.add("dragging")
      window.getSelection()?.removeAllRanges()
    }
    card.x = start.cardX + deltaX / start.zoom
    card.y = start.cardY + deltaY / start.zoom
    article.style.left = `${card.x}px`
    article.style.top = `${card.y}px`
  })
  const finish = async (event, cancelled = false) => {
    if (start?.id !== event.pointerId) return
    const gesture = start
    start = null
    article.classList.remove("dragging")
    if (article.hasPointerCapture(event.pointerId)) article.releasePointerCapture(event.pointerId)
    if (cancelled) {
      card.x = gesture.cardX
      card.y = gesture.cardY
      article.style.left = `${card.x}px`
      article.style.top = `${card.y}px`
      return
    }
    if (!gesture.moved) return
    const { x, y } = card
    renderCards()
    try { Object.assign(card, await request(`/api/cards/${card.id}`, json("PATCH", { x, y }))) }
    catch { setError("位置保存失败"); await refresh() }
  }
  article.addEventListener("pointerup", (event) => { void finish(event) })
  article.addEventListener("pointercancel", (event) => { void finish(event, true) })
  article.addEventListener("lostpointercapture", (event) => { void finish(event, true) })
}

async function handlePaste(event) {
  const point = state.pointer
  const image = Array.from(event.clipboardData?.items || []).find((item) => item.kind === "file" && item.type.startsWith("image/"))?.getAsFile()
  if (image) {
    event.preventDefault()
    await createImage(image, point)
    return
  }
  if (event.target.closest?.("textarea,input,[contenteditable='true']")) return
  const text = event.clipboardData?.getData("text/plain")?.trim()
  if (text) {
    event.preventDefault()
    await createText(text, point)
  }
}

async function createText(text, point) {
  try {
    const type = /^(https?:\/\/|www\.)\S+/i.test(text) ? "link" : "text"
    const position = openPoint(point || defaultInsertPoint(), type)
    const path = type === "link" ? "/api/cards/link" : "/api/cards/text"
    const body = type === "link" ? { dayKey: state.day, url: text, ...position } : { dayKey: state.day, textContent: text, ...position }
    const created = await request(path, json("POST", body))
    state.cards.push(created)
    renderCards()
    state.days = await request("/api/days")
    schedulePoll()
  } catch (error) { setError(error.message || "粘贴失败") }
}

async function createImage(file, point, { cutout = false, displayWidth = null, displayHeight = null } = {}) {
  try {
    const position = openPoint(point || defaultInsertPoint(), "image")
    const form = new FormData()
    form.append("dayKey", state.day)
    form.append("file", file)
    form.append("x", String(position.x))
    form.append("y", String(position.y))
    form.append("cutout", String(cutout))
    if (displayWidth) form.append("displayWidth", String(displayWidth))
    if (displayHeight) form.append("displayHeight", String(displayHeight))
    const created = await request("/api/cards/image", { method: "POST", body: form })
    state.cards.push(created)
    renderCards()
    state.days = await request("/api/days")
    schedulePoll()
  } catch (error) { setError(error.message || "图片粘贴失败") }
}

function openComposer(point) {
  board.querySelector(".composer")?.remove()
  const form = element("form", "composer")
  form.style.left = `${point.x}px`
  form.style.top = `${point.y}px`
  const input = document.createElement("textarea")
  input.placeholder = "记录内容"
  input.setAttribute("aria-label", "记录内容")
  const actions = element("div", "composer-actions")
  const close = iconButton("×", "关闭")
  const add = textElement("button", "button primary small", "+ 添加")
  add.type = "submit"
  actions.append(close, add)
  form.append(input, actions)
  close.addEventListener("click", () => form.remove())
  board.append(form)
  const composerPoint = keepBoardElementInViewport(form, point)
  form.addEventListener("submit", (event) => {
    event.preventDefault()
    const value = input.value.trim()
    if (value) { form.remove(); createText(value, composerPoint) }
  })
  input.focus()
}

function keepBoardElementInViewport(node, point) {
  const viewport = boardWrap.getBoundingClientRect()
  const rectangle = node.getBoundingClientRect()
  const margin = 16
  const shiftX = rectangle.right > viewport.right - margin
    ? viewport.right - margin - rectangle.right
    : Math.max(0, viewport.left + margin - rectangle.left)
  const shiftY = rectangle.bottom > viewport.bottom - margin
    ? viewport.bottom - margin - rectangle.bottom
    : Math.max(0, viewport.top + margin - rectangle.top)
  const adjusted = {
    x: point.x + shiftX / state.zoom,
    y: point.y + shiftY / state.zoom,
  }
  node.style.left = `${adjusted.x}px`
  node.style.top = `${adjusted.y}px`
  return adjusted
}

function keepOpenComposerInViewport() {
  const form = board.querySelector(".composer")
  if (!form) return
  keepBoardElementInViewport(form, {
    x: Number.parseFloat(form.style.left) || 0,
    y: Number.parseFloat(form.style.top) || 0,
  })
}

async function retryCard(card) {
  card.aiStatus = "pending"
  card.aiError = null
  renderCards()
  try { Object.assign(card, await request(`/api/cards/${card.id}/analyze`, { method: "POST" })); schedulePoll() }
  catch (error) { setError(error.message || "重试失败") }
}

async function removeCard(card) {
  try {
    await request(`/api/cards/${card.id}`, { method: "DELETE" })
    state.cards = state.cards.filter((item) => item.id !== card.id)
    state.days = await request("/api/days")
    renderCards()
  } catch (error) { setError(error.message || "删除失败") }
}

async function deleteKeyword(card, keyword) {
  const keywords = card.keywords.filter((value) => value !== keyword)
  try { Object.assign(card, await request(`/api/cards/${card.id}`, json("PATCH", { keywords }))); renderCards() }
  catch { setError("关键词保存失败") }
}

async function copyKeyword(keyword) {
  try { await navigator.clipboard.writeText(keyword); showToast(`已复制：${keyword}`) }
  catch { showToast("复制失败") }
}

function schedulePoll() {
  clearInterval(state.poll)
  const busy = state.cards.some((card) => card.aiStatus === "pending" || card.aiStatus === "generating")
  state.poll = setInterval(refresh, busy ? 2200 : 5000)
}

function openCalendar() {
  closeOverlay()
  let month = new Date(parseDay(state.day).getFullYear(), parseDay(state.day).getMonth(), 1)
  const backdrop = element("div", "calendar-backdrop overlay")
  const dialog = element("section", "calendar-dialog")
  dialog.setAttribute("role", "dialog")
  dialog.setAttribute("aria-label", "选择日期")
  backdrop.append(dialog)
  backdrop.addEventListener("pointerdown", (event) => { if (event.target === backdrop) closeOverlay() })
  document.querySelector(".app-shell").append(backdrop)
  const draw = () => {
    dialog.replaceChildren()
    const head = element("div", "calendar-head")
    const previous = iconButton("‹", "上个月")
    const title = textElement("strong", "", `${month.getFullYear()} 年 ${month.getMonth() + 1} 月`)
    const next = iconButton("›", "下个月")
    next.disabled = monthCode(month) >= monthCode(new Date(parseDay(state.today).getFullYear(), parseDay(state.today).getMonth(), 1))
    const close = iconButton("×", "关闭日历")
    close.classList.add("calendar-close")
    previous.addEventListener("click", () => { month = new Date(month.getFullYear(), month.getMonth() - 1, 1); draw() })
    next.addEventListener("click", () => { month = new Date(month.getFullYear(), month.getMonth() + 1, 1); draw() })
    close.addEventListener("click", closeOverlay)
    head.append(previous, title, next, close)
    const weekdays = element("div", "calendar-weekdays")
    for (const day of ["一", "二", "三", "四", "五", "六", "日"]) weekdays.append(textElement("span", "", day))
    const grid = element("div", "calendar-grid")
    for (const date of monthCells(month)) {
      if (!date) { grid.append(element("span", "calendar-blank")); continue }
      const key = dayKey(date)
      const button = textElement("button", `calendar-day${key === state.today ? " today" : ""}${key === state.day ? " selected" : ""}`, String(date.getDate()))
      button.setAttribute("aria-label", key)
      button.disabled = key > state.today || (key !== state.today && !state.days.includes(key))
      if (state.days.includes(key)) button.append(element("i", ""))
      button.addEventListener("click", () => { closeOverlay(); selectDay(key) })
      grid.append(button)
    }
    dialog.append(head, weekdays, grid)
  }
  draw()
}

async function openSettings() {
  closeOverlay()
  let preferences
  try {
    preferences = await request("/api/settings/capture")
  } catch (error) {
    setError(error.message || "设置加载失败")
    return
  }

  const backdrop = element("div", "settings-backdrop overlay")
  const dialog = element("section", "settings-dialog")
  dialog.setAttribute("role", "dialog")
  dialog.setAttribute("aria-label", "全局剪刀设置")
  const header = element("header", "settings-head")
  const heading = element("div", "")
  heading.append(
    textElement("strong", "", "全局剪刀"),
    textElement("span", "", "从网页、视频、PDF 或任意桌面软件剪下一块"),
  )
  const close = iconButton("×", "关闭设置")
  close.addEventListener("click", closeOverlay)
  header.append(heading, close)

  const form = element("form", "settings-form")
  const enabled = settingsToggle("启动 CtrlV 时启用全局截图快捷键", preferences.enabled)
  const toggles = element("div", "settings-toggles")
  toggles.append(enabled.label)

  const shortcut = settingsField("截图快捷键", "点击输入框后直接按下新的组合键")
  const hotkey = document.createElement("input")
  hotkey.name = "hotkey"
  hotkey.readOnly = true
  hotkey.value = preferences.hotkey
  hotkey.setAttribute("aria-label", "全局截图快捷键")
  hotkey.addEventListener("keydown", (event) => {
    event.preventDefault()
    const value = hotkeyFromEvent(event)
    if (value) hotkey.value = value
  })
  shortcut.append(hotkey)

  const destination = settingsField("保存到哪一天", "决定桌面裁剪完成后进入哪张白板")
  const dayMode = document.createElement("select")
  dayMode.name = "dayMode"
  for (const [value, label] of [["today", "始终保存到今天"], ["current", "保存到白板当前日期"]]) {
    const option = document.createElement("option")
    option.value = value
    option.textContent = label
    option.selected = preferences.dayMode === value
    dayMode.append(option)
  }
  destination.append(dayMode)

  const status = element("section", "capture-status")
  const statusTitle = preferences.status.registered
    ? `正在监听：${preferences.status.hotkey}`
    : preferences.status.error || (preferences.status.running ? "快捷键暂未注册" : "截图助手尚未启动")
  status.classList.toggle("ready", preferences.status.registered)
  status.append(
    textElement("strong", "", statusTitle),
    textElement("p", "", "按下快捷键后会冻结所有屏幕；画出选区并确认，透明 PNG 会直接进入本地白板。无需浏览器扩展，也不需要管理员权限。"),
  )

  const actions = element("footer", "settings-actions")
  const cancel = textElement("button", "button secondary", "取消")
  cancel.type = "button"
  cancel.addEventListener("click", closeOverlay)
  const save = textElement("button", "button primary", "保存设置")
  save.type = "submit"
  actions.append(cancel, save)
  form.append(toggles, shortcut, destination, status, actions)
  form.addEventListener("submit", async (event) => {
    event.preventDefault()
    save.disabled = true
    try {
      await request("/api/settings/capture", json("PATCH", {
        enabled: enabled.input.checked,
        hotkey: hotkey.value,
        dayMode: dayMode.value,
        lastDay: state.day,
      }))
      closeOverlay()
      showToast("全局剪刀设置已保存")
    } catch (error) {
      save.disabled = false
      setError(error.message || "设置保存失败")
    }
  })
  dialog.append(header, form)
  backdrop.append(dialog)
  backdrop.addEventListener("pointerdown", (event) => { if (event.target === backdrop) closeOverlay() })
  document.querySelector(".app-shell").append(backdrop)
}

function settingsField(title, description) {
  const label = element("label", "settings-field")
  const copy = element("span", "")
  copy.append(textElement("strong", "", title), textElement("small", "", description))
  label.append(copy)
  return label
}

function settingsToggle(text, checked) {
  const label = element("label", "settings-toggle")
  const input = document.createElement("input")
  input.type = "checkbox"
  input.checked = Boolean(checked)
  label.append(input, textElement("span", "", text))
  return { label, input }
}

function hotkeyFromEvent(event) {
  const key = event.key.toLowerCase()
  if (["control", "shift", "alt", "meta"].includes(key)) return ""
  if (!/^[a-z0-9]$/.test(key) && !/^f(?:[1-9]|1[0-2])$/.test(key)) return ""
  const parts = []
  if (event.ctrlKey) parts.push("ctrl")
  if (event.altKey) parts.push("alt")
  if (event.shiftKey) parts.push("shift")
  if (event.metaKey) parts.push("win")
  if (!parts.length) return ""
  return [...parts, key].join("+")
}

function openPreview(card) {
  closeOverlay()
  let view = { scale: 1, x: 0, y: 0 }
  let drag = null
  const backdrop = element("div", "preview-backdrop overlay")
  const stage = element("div", "preview-stage")
  const image = document.createElement("img")
  image.src = assetUrl(card.imageUrl)
  image.alt = card.summary || "放大的图片"
  image.draggable = false
  const redraw = () => { image.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }
  backdrop.addEventListener("click", (event) => { if (event.target !== image) closeOverlay() })
  image.addEventListener("click", (event) => event.stopPropagation())
  stage.addEventListener("wheel", (event) => { event.preventDefault(); view.scale = clamp(view.scale - event.deltaY * 0.0012, 0.55, 2.4); redraw() })
  stage.addEventListener("pointerdown", (event) => { stage.setPointerCapture(event.pointerId); drag = { x: event.clientX, y: event.clientY, left: view.x, top: view.y } })
  stage.addEventListener("pointermove", (event) => { if (drag) { view.x = drag.left + event.clientX - drag.x; view.y = drag.top + event.clientY - drag.y; redraw() } })
  stage.addEventListener("pointerup", () => { drag = null })
  stage.append(image)
  backdrop.append(stage)
  document.querySelector(".app-shell").append(backdrop)
}

async function selectDay(day) {
  state.day = day
  state.pointer = null
  hideSourceFloat()
  restoreCamera(day)
  await refresh()
  syncActiveDay()
}
function syncActiveDay() { request("/api/settings/capture", json("PATCH", { lastDay: state.day })).catch(() => {}) }
function closeOverlay() {
  const overlay = document.querySelector(".overlay")
  if (!overlay) return
  overlay.dispatchEvent(new Event("overlayclose"))
  overlay.remove()
}
function togglePaw(open) { pawMenu.classList.toggle("open", open); pawTrigger.setAttribute("aria-expanded", String(open)); pawMenu.querySelector(".paw-actions").setAttribute("aria-hidden", String(!open)) }

function openPoint(origin, type) {
  const width = type === "link" ? 320 : type === "text" ? 300 : 280
  const height = type === "image" ? 350 : type === "link" ? 220 : 190
  const candidates = [origin]
  for (let ring = 1; ring <= 6; ring += 1) {
    const distance = ring * 72
    candidates.push({ x: origin.x + distance, y: origin.y }, { x: origin.x, y: origin.y + distance }, { x: origin.x - distance, y: origin.y }, { x: origin.x, y: origin.y - distance })
  }
  for (const raw of candidates) {
    const point = { x: raw.x, y: raw.y }
    if (state.cards.every((card) => !overlap(point, width, height, card))) return point
  }
  return origin
}

function overlap(point, width, height, card) {
  const cardWidth = card.width
  const cardHeight = estimatedCardHeight(card)
  const gapX = 22
  const gapY = 22
  return !(point.x + width + gapX <= card.x || point.x >= card.x + cardWidth + gapX || point.y + height + gapY <= card.y || point.y >= card.y + cardHeight + gapY)
}

async function request(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    const raw = await response.text()
    let message = response.statusText || "请求失败"
    try { message = JSON.parse(raw).detail || message } catch { message = raw.trim() || message }
    throw new Error([502, 503, 504].includes(response.status) ? "后台服务未连接" : message)
  }
  return response.status === 204 ? undefined : response.json()
}

function json(method, body) { return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } }
function assetUrl(path) { return path && API_BASE && !path.startsWith("http") ? `${API_BASE}${path}` : path || "" }
function cardRenderKey(card) { return JSON.stringify([card.type, card.textContent, card.imageUrl, card.isCutout, card.sourceUrl, card.sourceTitle, card.sourceDescription, card.sourceApp, card.sourceFile, card.sourceCapturedAt, card.summary, card.keywords, card.aiStatus, card.aiError]) }
function clientPoint(x, y) { const rect = board.getBoundingClientRect(); return { x: (x - rect.left) / state.zoom, y: (y - rect.top) / state.zoom } }
function element(tag, className) { const node = document.createElement(tag); if (className) node.className = className; return node }
function textElement(tag, className, text) { const node = element(tag, className); node.textContent = text; return node }
function iconButton(text, title) { const button = textElement("button", "button icon", text); button.type = "button"; button.title = title; button.setAttribute("aria-label", title); return button }
function setError(text) { showNotice(".error-banner", text, 0) }
function showToast(text) { showNotice(".toast", text, 1800) }
function showNotice(selector, text, timeout) { const notice = document.querySelector(selector); notice.textContent = text; notice.hidden = !text; if (text && timeout) setTimeout(() => { notice.hidden = true }, timeout) }
function parseDay(value) { const [year, month, day] = value.split("-").map(Number); return new Date(year, month - 1, day) }
function dayKey(value) { return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}` }
function monthCode(value) { return value.getFullYear() * 12 + value.getMonth() }
function monthCells(month) { const cells = Array.from({ length: (month.getDay() + 6) % 7 }, () => null); const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate(); for (let day = 1; day <= count; day += 1) cells.push(new Date(month.getFullYear(), month.getMonth(), day)); while (cells.length % 7) cells.push(null); return cells }
function clamp(value, min, max) { return Math.min(max, Math.max(min, value)) }

async function migrateLegacyPositions(cards) {
  const legacy = cards.filter((card) => card.positionSpace !== "world")
  if (!legacy.length) return cards
  const viewport = boardWrap.getBoundingClientRect()
  const homeLeft = (WORLD_WIDTH - viewport.width) / 2
  const homeTop = (WORLD_HEIGHT - viewport.height) / 2
  await Promise.all(legacy.map(async (card) => {
    card.x = homeLeft + card.x * viewport.width
    card.y = homeTop + card.y * viewport.height
    card.positionSpace = "world"
    try {
      Object.assign(card, await request(`/api/cards/${card.id}`, json("PATCH", {
        x: card.x,
        y: card.y,
        positionSpace: "world",
      })))
    } catch {
      setError("部分旧卡片的位置迁移失败")
    }
  }))
  return cards
}

function defaultInsertPoint() {
  const center = cameraCenter()
  return { x: center.x - 140, y: center.y - 100 }
}

function cameraCenter() {
  const viewport = boardWrap.getBoundingClientRect()
  return {
    x: (viewport.width / 2 - state.panX) / state.zoom,
    y: (viewport.height / 2 - state.panY) / state.zoom,
  }
}

function cameraStorageKey(day) {
  return `ctrlv-camera:${day}`
}

function restoreCamera(day) {
  const viewport = boardWrap.getBoundingClientRect()
  let saved = null
  try { saved = JSON.parse(localStorage.getItem(cameraStorageKey(day)) || "null") } catch {}
  const centerX = Number.isFinite(saved?.centerX) ? saved.centerX : WORLD_WIDTH / 2
  const centerY = Number.isFinite(saved?.centerY) ? saved.centerY : WORLD_HEIGHT / 2
  state.zoom = clamp(Number(saved?.zoom) || 1, MIN_ZOOM, MAX_ZOOM)
  state.panX = viewport.width / 2 - centerX * state.zoom
  state.panY = viewport.height / 2 - centerY * state.zoom
  constrainCamera()
  applyBoardTransform()
}

function saveCamera() {
  const center = cameraCenter()
  localStorage.setItem(cameraStorageKey(state.day), JSON.stringify({
    zoom: state.zoom,
    centerX: center.x,
    centerY: center.y,
  }))
}

function constrainCamera() {
  const viewport = boardWrap.getBoundingClientRect()
  const visibleX = Math.min(180, viewport.width * 0.25)
  const visibleY = Math.min(140, viewport.height * 0.25)
  const scaledWidth = WORLD_WIDTH * state.zoom
  const scaledHeight = WORLD_HEIGHT * state.zoom
  state.panX = clamp(state.panX, visibleX - scaledWidth, viewport.width - visibleX)
  state.panY = clamp(state.panY, visibleY - scaledHeight, viewport.height - visibleY)
}

function fitCards() {
  if (!state.cards.length) return
  const bounds = state.cards.reduce((result, card) => {
    const height = estimatedCardHeight(card)
    return {
      left: Math.min(result.left, card.x),
      top: Math.min(result.top, card.y),
      right: Math.max(result.right, card.x + card.width),
      bottom: Math.max(result.bottom, card.y + height),
    }
  }, { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity })
  const viewport = boardWrap.getBoundingClientRect()
  const padding = 120
  const contentWidth = Math.max(1, bounds.right - bounds.left)
  const contentHeight = Math.max(1, bounds.bottom - bounds.top)
  state.zoom = clamp(
    Math.min(viewport.width / (contentWidth + padding * 2), viewport.height / (contentHeight + padding * 2)),
    MIN_ZOOM,
    MAX_ZOOM,
  )
  const centerX = (bounds.left + bounds.right) / 2
  const centerY = (bounds.top + bounds.bottom) / 2
  state.panX = viewport.width / 2 - centerX * state.zoom
  state.panY = viewport.height / 2 - centerY * state.zoom
  constrainCamera()
  applyBoardTransform()
  saveCamera()
  hideSourceFloat()
}

function estimatedCardHeight(card) {
  if (card.isCutout && card.mediaWidth && card.mediaHeight) return card.width * card.mediaHeight / card.mediaWidth
  return card.type === "image" ? 350 : card.type === "link" ? 220 : 190
}

function startCameraPan(event) {
  const wantsMiddleButton = event.button === 1
  const wantsSpaceDrag = event.button === 0 && state.spacePressed
  const wantsBlankDrag = event.button === 0 && !event.target.closest(INTERACTIVE)
  if (!wantsMiddleButton && !wantsSpaceDrag && !wantsBlankDrag) return
  event.preventDefault()
  boardWrap.setPointerCapture(event.pointerId)
  state.panGesture = {
    id: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    panX: state.panX,
    panY: state.panY,
    moved: false,
  }
  boardWrap.classList.add("panning")
  hideSourceFloat()
}

function moveCameraPan(event) {
  if (state.panGesture?.id !== event.pointerId) {
    if (!event.target.closest(INTERACTIVE)) state.pointer = clientPoint(event.clientX, event.clientY)
    return
  }
  const deltaX = event.clientX - state.panGesture.startX
  const deltaY = event.clientY - state.panGesture.startY
  if (Math.hypot(deltaX, deltaY) > 3) state.panGesture.moved = true
  state.panX = state.panGesture.panX + deltaX
  state.panY = state.panGesture.panY + deltaY
  constrainCamera()
  applyBoardTransform()
}

function finishCameraPan(event) {
  if (state.panGesture?.id !== event.pointerId) return
  if (state.panGesture.moved) state.suppressDoubleClickUntil = performance.now() + 350
  state.panGesture = null
  boardWrap.classList.remove("panning")
  saveCamera()
}

function zoomBoard(event) {
  if (event.target.closest(".overlay")) return
  event.preventDefault()
  hideSourceFloat()
  const previous = state.zoom
  const next = clamp(previous * Math.exp(-event.deltaY * 0.00115), MIN_ZOOM, MAX_ZOOM)
  if (Math.abs(next - previous) < 0.001) return
  const viewport = boardWrap.getBoundingClientRect()
  const center = cameraCenter()
  state.zoom = next
  state.panX = viewport.width / 2 - center.x * next
  state.panY = viewport.height / 2 - center.y * next
  constrainCamera()
  applyBoardTransform()
  state.pointer = clientPoint(event.clientX, event.clientY)
  saveCamera()
}

function applyBoardTransform() {
  const minReadableCardZoom = minimumReadableCardZoom()
  const cardReadabilityScale = Math.max(1, minReadableCardZoom / state.zoom)
  board.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`
  board.style.setProperty("--camera-ui-scale", String(1 / state.zoom))
  board.style.setProperty("--card-readability-scale", String(cardReadabilityScale))
  board.style.setProperty("--card-action-scale", String(1 / (state.zoom * cardReadabilityScale)))
  board.style.setProperty(
    "--card-image-max-height",
    `${state.zoom < minReadableCardZoom ? COMPACT_CARD_IMAGE_HEIGHT : 350}px`,
  )
}

function minimumReadableCardZoom() {
  const viewportWidth = boardWrap.getBoundingClientRect().width || window.innerWidth
  const targetWidth = clamp(viewportWidth * CARD_VIEWPORT_RATIO, MIN_CARD_SCREEN_WIDTH, MAX_CARD_SCREEN_WIDTH)
  return targetWidth / REFERENCE_CARD_WIDTH
}
