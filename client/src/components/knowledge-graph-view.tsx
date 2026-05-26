import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force"
import { ExternalLink, Network, Search } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import type { PointerEvent as ReactPointerEvent } from "react"

import type { CaptureCard } from "../types/cards"
import type { KnowledgeGraphEdge, KnowledgeGraphNode, KnowledgeGraphResponse } from "../types/knowledge"
import { Button } from "./ui/button"

const GRAPH_WIDTH = 1040
const GRAPH_HEIGHT = 680

type GraphNodeDatum = KnowledgeGraphNode & SimulationNodeDatum & { radius: number }
type GraphLinkDatum = KnowledgeGraphEdge & SimulationLinkDatum<GraphNodeDatum>

type KnowledgeGraphViewProps = {
  graph: KnowledgeGraphResponse | null
  isLoading: boolean
  onOpenCard: (card: CaptureCard) => void
  onSearchKeyword: (keyword: string) => void
}

export function KnowledgeGraphView({ graph, isLoading, onOpenCard, onSearchKeyword }: KnowledgeGraphViewProps) {
  const [layout, setLayout] = useState<{ nodes: GraphNodeDatum[]; links: GraphLinkDatum[] }>({ nodes: [], links: [] })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const simulationRef = useRef<Simulation<GraphNodeDatum, GraphLinkDatum> | null>(null)
  const dragRef = useRef<{ node: GraphNodeDatum; pointerId: number } | null>(null)

  useEffect(() => {
    if (!graph) {
      return
    }

    const nodes: GraphNodeDatum[] = graph.nodes.map((node, index) => ({
      ...node,
      radius: node.type === "keyword" ? Math.min(34, 16 + node.count * 2) : node.type === "page" ? Math.min(30, 18 + node.count) : 8,
      x: GRAPH_WIDTH / 2 + Math.cos(index) * 90,
      y: GRAPH_HEIGHT / 2 + Math.sin(index) * 90,
    }))
    const links: GraphLinkDatum[] = graph.edges.map((edge) => ({ ...edge }))

    simulationRef.current?.stop()
    const simulation = forceSimulation<GraphNodeDatum, GraphLinkDatum>(nodes)
      .force(
        "link",
        forceLink<GraphNodeDatum, GraphLinkDatum>(links)
          .id((node) => node.id)
          .distance((link) => (getNodeType(link.source) === "keyword" ? 96 : 82))
          .strength(0.55),
      )
      .force("charge", forceManyBody<GraphNodeDatum>().strength((node) => (node.type === "keyword" ? -420 : node.type === "page" ? -360 : -140)))
      .force("collide", forceCollide<GraphNodeDatum>().radius((node) => node.radius + 12))
      .force("x", forceX<GraphNodeDatum>(GRAPH_WIDTH / 2).strength(0.035))
      .force("y", forceY<GraphNodeDatum>(GRAPH_HEIGHT / 2).strength(0.045))
      .force("center", forceCenter(GRAPH_WIDTH / 2, GRAPH_HEIGHT / 2))
      .on("tick", () => setLayout({ nodes: [...nodes], links: [...links] }))

    simulationRef.current = simulation

    return () => {
      simulation.stop()
    }
  }, [graph])

  const selectedNode =
    layout.nodes.find((node) => node.id === selectedId) ??
    layout.nodes.find((node) => node.type === "keyword" || node.type === "page") ??
    layout.nodes[0] ??
    null
  const activeSelectedId = selectedNode?.id ?? null
  const detailItems = useMemo(() => {
    if (!graph || !selectedNode) return []
    if (selectedNode.type === "item") {
      return selectedNode.knowledgeItem ? [selectedNode] : []
    }
    const itemNodeIds = graph.edges
      .filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id)
      .map((edge) => (edge.source === selectedNode.id ? edge.target : edge.source))
      .filter((id) => String(id).startsWith("item:"))
    return itemNodeIds
      .map((id) => graph.nodes.find((node) => node.id === id))
      .filter((node): node is KnowledgeGraphNode => Boolean(node?.knowledgeItem))
  }, [graph, selectedNode])

  const linkLines = layout.links
    .map((link) => {
      const source = resolveLinkNode(link.source, layout.nodes)
      const target = resolveLinkNode(link.target, layout.nodes)
      if (!source || !target) return null
      return { ...link, source, target }
    })
    .filter((link): link is GraphLinkDatum & { source: GraphNodeDatum; target: GraphNodeDatum } => Boolean(link))

  const toSvgPoint = (event: ReactPointerEvent<SVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return { x: GRAPH_WIDTH / 2, y: GRAPH_HEIGHT / 2 }
    return {
      x: ((event.clientX - rect.left) / rect.width) * GRAPH_WIDTH,
      y: ((event.clientY - rect.top) / rect.height) * GRAPH_HEIGHT,
    }
  }

  const handleNodePointerDown = (node: GraphNodeDatum, event: ReactPointerEvent<SVGCircleElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    const point = toSvgPoint(event)
    node.fx = point.x
    node.fy = point.y
    dragRef.current = { node, pointerId: event.pointerId }
    setSelectedId(node.id)
    simulationRef.current?.alphaTarget(0.25).restart()
  }

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const state = dragRef.current
    if (!state || state.pointerId !== event.pointerId) return
    const point = toSvgPoint(event)
    state.node.fx = point.x
    state.node.fy = point.y
  }

  const handlePointerUp = (event: ReactPointerEvent<SVGSVGElement>) => {
    const state = dragRef.current
    if (!state || state.pointerId !== event.pointerId) return
    state.node.fx = null
    state.node.fy = null
    dragRef.current = null
    simulationRef.current?.alphaTarget(0)
  }

  if (isLoading) {
    return (
      <section className="graph-view">
        <div className="soft-empty">正在整理关系...</div>
      </section>
    )
  }

  if (!graph || graph.nodes.length === 0) {
    return (
      <section className="graph-view graph-empty">
        <div className="soft-empty">
          <Network size={30} />
          <span>暂时没有形成正式知识关联</span>
        </div>
      </section>
    )
  }

  return (
    <section className="graph-view" aria-label="知识图谱">
      <div className="graph-canvas">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`}
          role="img"
          aria-label="关键词与卡片关联图谱"
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          <g className="graph-links">
            {linkLines.map((link) => (
              <line key={link.id} x1={link.source.x} y1={link.source.y} x2={link.target.x} y2={link.target.y} />
            ))}
          </g>
          <g className="graph-nodes">
            {layout.nodes.map((node) => (
              <g key={node.id} transform={`translate(${node.x ?? 0}, ${node.y ?? 0})`}>
                <circle
                  r={node.radius}
                  className={`${node.type === "keyword" ? "keyword-node" : node.type === "page" ? "page-node" : "item-node"}${node.id === activeSelectedId ? " selected" : ""}`}
                  onPointerDown={(event) => handleNodePointerDown(node, event)}
                />
                <text y={node.type === "item" ? 21 : node.radius + 16}>{node.label}</text>
              </g>
            ))}
          </g>
        </svg>
      </div>

      <aside className="graph-detail">
        {selectedNode ? (
          <>
            <span className="view-kicker">{selectedNode.type === "keyword" ? "Keyword Node" : selectedNode.type === "page" ? "Knowledge Page" : "Knowledge Item"}</span>
            <h2>{selectedNode.label}</h2>
            {selectedNode.type === "keyword" ? (
              <>
                <div className="graph-detail-stats">
                  <span>{selectedNode.count} 条知识</span>
                  <span>{selectedNode.weeks.length} 个周</span>
                </div>
                <Button type="button" variant="secondary" size="sm" onClick={() => onSearchKeyword(selectedNode.label)}>
                  <Search size={15} />
                  搜索这个词
                </Button>
              </>
            ) : selectedNode.type === "page" ? (
              <div className="graph-detail-stats">
                <span>{selectedNode.status || "draft"}</span>
                <span>{selectedNode.itemCount} 条知识</span>
              </div>
            ) : selectedNode.card ? (
              <Button type="button" variant="secondary" size="sm" onClick={() => onOpenCard(selectedNode.card as CaptureCard)}>
                <ExternalLink size={15} />
                回到原卡片
              </Button>
            ) : null}

            <div className="graph-detail-list">
              {detailItems.map((node) => (
                <button type="button" key={node.id} onClick={() => node.card && onOpenCard(node.card)}>
                  <strong>{node.knowledgeItem?.summary || node.knowledgeItem?.title || "知识条目"}</strong>
                  <span>{node.card ? node.card.weekKey : node.knowledgeItem?.sourceRef || node.knowledgeItem?.source}</span>
                </button>
              ))}
            </div>
          </>
        ) : null}
      </aside>
    </section>
  )
}

function resolveLinkNode(value: string | number | GraphNodeDatum, nodes: GraphNodeDatum[]) {
  if (typeof value === "object") return value
  return nodes.find((node) => node.id === value)
}

function getNodeType(value: string | number | GraphNodeDatum) {
  if (typeof value === "object") return value.type
  const id = String(value)
  if (id.startsWith("page:")) return "page"
  if (id.startsWith("item:")) return "item"
  return "keyword"
}


