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

import type { SearchKnowledgeNetwork, SearchNetworkEdge, SearchNetworkNode } from "../types/knowledge-network"
import type { KnowledgeSearchResult } from "../types/retrieval"
import { Button } from "./ui/button"

const NETWORK_WIDTH = 1040
const NETWORK_HEIGHT = 520

type NetworkNodeDatum = SearchNetworkNode & SimulationNodeDatum & { radius: number }
type NetworkLinkDatum = SearchNetworkEdge & SimulationLinkDatum<NetworkNodeDatum>

type SearchKnowledgeNetworkProps = {
  network: SearchKnowledgeNetwork
  onOpenResult: (result: KnowledgeSearchResult) => void
  onSearchKeyword: (keyword: string) => void
}

export function SearchKnowledgeNetwork({ network, onOpenResult, onSearchKeyword }: SearchKnowledgeNetworkProps) {
  const [layout, setLayout] = useState<{ nodes: NetworkNodeDatum[]; links: NetworkLinkDatum[] }>({ nodes: [], links: [] })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const simulationRef = useRef<Simulation<NetworkNodeDatum, NetworkLinkDatum> | null>(null)
  const dragRef = useRef<{ node: NetworkNodeDatum; pointerId: number } | null>(null)

  useEffect(() => {
    if (network.nodes.length === 0) {
      simulationRef.current?.stop()
      return
    }

    const nodes: NetworkNodeDatum[] = network.nodes.map((node, index) => ({
      ...node,
      radius: node.type === "query" ? 36 : node.type === "keyword" ? Math.min(30, 15 + node.count * 2) : 8,
      x: NETWORK_WIDTH / 2 + Math.cos(index) * 80,
      y: NETWORK_HEIGHT / 2 + Math.sin(index) * 80,
    }))
    const links: NetworkLinkDatum[] = network.edges.map((edge) => ({ ...edge }))

    simulationRef.current?.stop()
    const simulation = forceSimulation<NetworkNodeDatum, NetworkLinkDatum>(nodes)
      .force(
        "link",
        forceLink<NetworkNodeDatum, NetworkLinkDatum>(links)
          .id((node) => node.id)
          .distance((link) => (getNodeType(link.source) === "query" ? 120 : 86))
          .strength((link) => (getNodeType(link.source) === "query" ? 0.42 : 0.58)),
      )
      .force("charge", forceManyBody<NetworkNodeDatum>().strength((node) => (node.type === "query" ? -520 : node.type === "keyword" ? -340 : -120)))
      .force("collide", forceCollide<NetworkNodeDatum>().radius((node) => node.radius + 12))
      .force("x", forceX<NetworkNodeDatum>(NETWORK_WIDTH / 2).strength(0.04))
      .force("y", forceY<NetworkNodeDatum>(NETWORK_HEIGHT / 2).strength(0.05))
      .force("center", forceCenter(NETWORK_WIDTH / 2, NETWORK_HEIGHT / 2))
      .on("tick", () => setLayout({ nodes: [...nodes], links: [...links] }))

    simulationRef.current = simulation

    return () => {
      simulation.stop()
    }
  }, [network])

  const selectedNode = layout.nodes.find((node) => node.id === selectedId) ?? layout.nodes.find((node) => node.type === "query") ?? layout.nodes[0] ?? null
  const activeSelectedId = selectedNode?.id ?? null
  const detailItems = useMemo(() => {
    if (!selectedNode) return []
    if (selectedNode.type === "item") {
      return selectedNode.result ? [selectedNode] : []
    }
    const itemNodeIds = network.edges
      .filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id)
      .map((edge) => (edge.source === selectedNode.id ? edge.target : edge.source))
      .filter((id) => String(id).startsWith("item:"))
    return itemNodeIds
      .map((id) => network.nodes.find((node) => node.id === id))
      .filter((node): node is SearchNetworkNode => Boolean(node?.result))
  }, [network, selectedNode])

  const linkLines = layout.links
    .map((link) => {
      const source = resolveLinkNode(link.source, layout.nodes)
      const target = resolveLinkNode(link.target, layout.nodes)
      if (!source || !target) return null
      return { ...link, source, target }
    })
    .filter((link): link is NetworkLinkDatum & { source: NetworkNodeDatum; target: NetworkNodeDatum } => Boolean(link))

  const toSvgPoint = (event: ReactPointerEvent<SVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return { x: NETWORK_WIDTH / 2, y: NETWORK_HEIGHT / 2 }
    return {
      x: ((event.clientX - rect.left) / rect.width) * NETWORK_WIDTH,
      y: ((event.clientY - rect.top) / rect.height) * NETWORK_HEIGHT,
    }
  }

  const handleNodePointerDown = (node: NetworkNodeDatum, event: ReactPointerEvent<SVGCircleElement>) => {
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

  if (network.nodes.length === 0) {
    return null
  }

  return (
    <section className="network-view" aria-label="搜索关联网络">
      <div className="network-canvas">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${NETWORK_WIDTH} ${NETWORK_HEIGHT}`}
          role="img"
          aria-label="当前搜索结果关联网络"
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          <g className="network-links">
            {linkLines.map((link) => (
              <line key={link.id} x1={link.source.x} y1={link.source.y} x2={link.target.x} y2={link.target.y} />
            ))}
          </g>
          <g className="network-nodes">
            {layout.nodes.map((node) => (
              <g key={node.id} transform={`translate(${node.x ?? 0}, ${node.y ?? 0})`}>
                <circle
                  r={node.radius}
                  className={`${node.type}-node${node.id === activeSelectedId ? " selected" : ""}`}
                  onPointerDown={(event) => handleNodePointerDown(node, event)}
                />
                <text y={node.type === "item" ? 21 : node.radius + 16}>{node.label}</text>
              </g>
            ))}
          </g>
        </svg>
      </div>

      <aside className="network-detail">
        {selectedNode ? (
          <>
            <span className="view-kicker">{selectedNode.type === "query" ? "搜索网络" : selectedNode.type === "keyword" ? "关联关键词" : "知识条目"}</span>
            <h2>{selectedNode.label}</h2>
            {selectedNode.type === "query" ? (
              <div className="network-detail-stats">
                <span>{selectedNode.count} 条搜索结果</span>
                <span>{selectedNode.weeks.length} 个周</span>
              </div>
            ) : selectedNode.type === "keyword" ? (
              <>
                <div className="network-detail-stats">
                  <span>{selectedNode.count} 条关联知识</span>
                  <span>{selectedNode.weeks.length} 个周</span>
                </div>
                <Button type="button" variant="secondary" size="sm" onClick={() => onSearchKeyword(selectedNode.label)}>
                  <Search size={15} />
                  搜索这个词
                </Button>
              </>
            ) : selectedNode.result?.card ? (
              <Button type="button" variant="secondary" size="sm" onClick={() => selectedNode.result && onOpenResult(selectedNode.result)}>
                <ExternalLink size={15} />
                回到原卡片
              </Button>
            ) : null}

            <div className="network-detail-list">
              {detailItems.map((node) => (
                <button type="button" key={node.id} onClick={() => node.result && onOpenResult(node.result)}>
                  <strong>{node.knowledgeItem?.summary || node.knowledgeItem?.title || "知识条目"}</strong>
                  <span>{node.card ? node.card.weekKey : node.knowledgeItem?.sourceRef || node.knowledgeItem?.source}</span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <div className="soft-empty">
            <Network size={28} />
            <span>这次搜索还没有可串联的结果</span>
          </div>
        )}
      </aside>
    </section>
  )
}

function resolveLinkNode(value: string | number | NetworkNodeDatum, nodes: NetworkNodeDatum[]) {
  if (typeof value === "object") return value
  return nodes.find((node) => node.id === value)
}

function getNodeType(value: string | number | NetworkNodeDatum) {
  if (typeof value === "object") return value.type
  const id = String(value)
  if (id.startsWith("query:")) return "query"
  if (id.startsWith("item:")) return "item"
  return "keyword"
}
