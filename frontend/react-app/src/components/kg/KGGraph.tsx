import { useCallback, useEffect, useMemo, useState, useRef } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Node,
  OnSelectionChangeParams,
  useEdgesState,
  useNodesState,
} from 'reactflow'
import {
  forceSimulation,
  forceManyBody,
  forceLink,
  forceCenter,
  SimulationNodeDatum,
  SimulationLinkDatum,
} from 'd3-force'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, FileText, GitBranch, Hash, Network, Filter } from 'lucide-react'
import { fetchGraph, GraphEdge, GraphNode } from '../../api/query'
import { KGSkeleton } from '../ui/Skeleton'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { useToastStore } from '../../store/toastStore'
import { useStore } from '../../store'
import { cn } from '../../lib/utils'
import GraphCircleNode from './GraphCircleNode'
import GraphFilter from './GraphFilter'
import 'reactflow/dist/style.css'

type Selection =
  | { kind: 'node'; id: string }
  | { kind: 'edge'; id: string }
  | null

interface SimNode extends SimulationNodeDatum {
  id: string
  label: string
  type: string
  degree: number
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  id: string
  relation: string
  weight?: number
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function edgeId(edge: GraphEdge, index: number) {
  return edge.id || `${edge.source}-${edge.relation}-${edge.target}-${index}`
}

function arrayLabel(values: Array<string | number> | undefined, empty = 'None') {
  if (!values?.length) return empty
  return values.join(', ')
}

function EmptyState() {
  return (
    <div className="flex h-full items-center justify-center px-6 text-center">
      <div className="max-w-sm space-y-3 text-sm text-muted-foreground">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg border border-border/70 bg-background">
          <GitBranch size={20} className="text-emerald-600" />
        </div>
        <div className="text-sm font-semibold text-foreground">Knowledge Graph chưa có dữ liệu</div>
        <p className="text-xs leading-5">
          Hãy ingest tài liệu bằng chế độ Hybrid Graph để tạo node, relation và evidence cho tab này.
        </p>
      </div>
    </div>
  )
}

function ErrorState({ message }: { message?: string }) {
  return (
    <div className="flex h-full items-center justify-center px-6 text-center">
      <div className="max-w-md space-y-3 text-sm text-muted-foreground">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg border border-red-200 bg-red-50 text-red-600">
          <AlertTriangle size={20} />
        </div>
        <div className="text-sm font-semibold text-red-600">Không tải được Neo4j Knowledge Graph</div>
        <p className="text-xs leading-5">
          Kiểm tra Neo4j container/Bolt connection, sau đó reload tab. Chi tiết: {message || 'Graph API unavailable.'}
        </p>
      </div>
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: string | number }) {
  const displayValue = value === '' || value === null || value === undefined ? 'None' : value
  return (
    <div className="grid grid-cols-[86px_1fr] gap-3 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 break-words font-medium text-foreground">{displayValue}</span>
    </div>
  )
}

function DetailPanel({ node, edge }: { node?: GraphNode; edge?: GraphEdge }) {
  if (!node && !edge) {
    return (
      <aside className="absolute right-3 top-3 z-10 w-[290px] rounded-lg border border-border/70 bg-background/95 p-4 shadow-lg backdrop-blur">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Network size={16} />
          Graph detail
        </div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          Chọn một node hoặc relation để xem metadata, nguồn tài liệu và evidence preview.
        </p>
      </aside>
    )
  }

  if (node) {
    return (
      <aside className="absolute right-3 top-3 z-10 max-h-[calc(100%-24px)] w-[290px] overflow-auto rounded-lg border border-border/70 bg-background/95 p-4 shadow-lg backdrop-blur">
        <div className="mb-3 flex items-start gap-2">
          <Hash size={16} className="mt-0.5 shrink-0 text-emerald-600" />
          <div className="min-w-0">
            <div className="break-words text-sm font-semibold leading-5 text-foreground">{node.label}</div>
            <div className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{node.type || 'Concept'}</div>
          </div>
        </div>
        <div className="space-y-2.5">
          <DetailRow label="Mentions" value={node.mentions ?? 0} />
          <DetailRow label="Degree" value={node.degree ?? 0} />
          <DetailRow label="Files" value={arrayLabel(node.source_files)} />
          <DetailRow label="Pages" value={arrayLabel(node.pages)} />
        </div>
      </aside>
    )
  }

  return (
    <aside className="absolute right-3 top-3 z-10 max-h-[calc(100%-24px)] w-[310px] overflow-auto rounded-lg border border-border/70 bg-background/95 p-4 shadow-lg backdrop-blur">
      <div className="mb-3 flex items-start gap-2">
        <FileText size={16} className="mt-0.5 shrink-0 text-emerald-600" />
        <div className="min-w-0">
          <div className="break-words text-sm font-semibold leading-5 text-foreground">{edge?.relation || 'Relation'}</div>
          <div className="mt-0.5 break-words text-[11px] text-muted-foreground">{edge?.source} {'->'} {edge?.target}</div>
        </div>
      </div>
      <div className="space-y-2.5">
        <DetailRow label="Weight" value={edge?.weight ?? 0} />
        <DetailRow label="File" value={edge?.source_file || 'None'} />
        <DetailRow label="Page" value={edge?.page || 'None'} />
        <DetailRow label="Chunks" value={arrayLabel(edge?.chunk_ids)} />
        <div className="pt-1">
          <div className="mb-1 text-xs text-muted-foreground">Evidence</div>
          <p className="rounded-md border border-border/60 bg-muted/30 p-2 text-xs leading-5 text-foreground">
            {edge?.evidence_preview || 'No evidence preview available.'}
          </p>
        </div>
      </div>
    </aside>
  )
}

export default function KGGraph() {
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const pushToast = useToastStore((s) => s.pushToast)
  const graphFocus = useStore((s) => s.graphFocus)
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['graph', activeWorkspaceId],
    queryFn: () => fetchGraph(activeWorkspaceId),
    staleTime: 60_000,
  })

  const [selection, setSelection] = useState<Selection>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set())
  const [isFilterOpen, setIsFilterOpen] = useState(false)

  const nodeTypes = useMemo(() => ({ circleNode: GraphCircleNode }), [])

  const edgeById = useMemo(() => {
    const pairs = data?.edges?.map((edge, index) => [edgeId(edge, index), edge] as const) ?? []
    return new Map(pairs)
  }, [data?.edges])

  const nodeById = useMemo(() => new Map((data?.nodes ?? []).map((node) => [node.id, node] as const)), [data?.nodes])
  const selectedNode = selection?.kind === 'node' ? nodeById.get(selection.id) : undefined
  const selectedEdge = selection?.kind === 'edge' ? edgeById.get(selection.id) : undefined

  // Track current node positions in ref to avoid re-running force simulation loop
  const nodesRef = useRef<Node[]>([])
  const simulationRef = useRef<any>(null)
  useEffect(() => {
    nodesRef.current = nodes
  }, [nodes])

  // Initialize selected types when graph data changes
  const lastDataRef = useRef<any>(null)
  const availableTypes = useMemo(() => {
    return Array.from(new Set((data?.nodes ?? []).map((n) => n.type || 'Concept')))
  }, [data?.nodes])

  useEffect(() => {
    if (data && data !== lastDataRef.current) {
      lastDataRef.current = data
      const types = Array.from(new Set((data.nodes ?? []).map((n) => n.type || 'Concept')))
      setSelectedTypes(new Set(types))
    }
  }, [data])

  // Filter nodes and edges based on selected types
  const filteredNodes = useMemo(() => {
    return (data?.nodes ?? []).filter((node) => selectedTypes.has(node.type || 'Concept'))
  }, [data?.nodes, selectedTypes])

  const filteredEdges = useMemo(() => {
    return (data?.edges ?? []).filter((edge) => {
      const sourceNode = nodeById.get(edge.source)
      const targetNode = nodeById.get(edge.target)
      if (!sourceNode || !targetNode) return false
      return (
        selectedTypes.has(sourceNode.type || 'Concept') &&
        selectedTypes.has(targetNode.type || 'Concept')
      )
    })
  }, [data?.edges, nodeById, selectedTypes])

  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)

  const connectedNodeIds = useMemo(() => {
    const set = new Set<string>()
    if (hoveredNodeId) {
      set.add(hoveredNodeId)
      filteredEdges.forEach((edge) => {
        if (edge.source === hoveredNodeId) {
          set.add(edge.target)
        } else if (edge.target === hoveredNodeId) {
          set.add(edge.source)
        }
      })
    }
    return set
  }, [hoveredNodeId, filteredEdges])

  useEffect(() => {
    if (!isError) return
    pushToast({
      type: 'error',
      title: 'Knowledge Graph unavailable',
      description: error instanceof Error ? error.message : 'The graph panel could not load data.',
    })
  }, [error, isError, pushToast])

  // D3 force simulation layout
  useEffect(() => {
    if (!filteredNodes.length) {
      setNodes([])
      setEdges([])
      return
    }

    const focusNodeIds = new Set(graphFocus?.nodeIds ?? [])

    // Reuse existing node positions for stability
    const existingPositions = new Map<string, { x: number; y: number }>()
    nodesRef.current.forEach((n) => {
      if (n.position) {
        existingPositions.set(n.id, n.position)
      }
    })

    // Prepare simulation nodes
    const simNodes: SimNode[] = filteredNodes.map((node) => {
      const pos = existingPositions.get(node.id)
      return {
        id: node.id,
        label: node.label || node.id,
        type: node.type || 'Concept',
        degree: node.degree || 0,
        x: pos ? pos.x : Math.random() * 200 - 100,
        y: pos ? pos.y : Math.random() * 200 - 100,
      }
    })

    // Prepare simulation links
    const simLinks: SimLink[] = filteredEdges.map((edge, index) => {
      return {
        id: edgeId(edge, index),
        source: edge.source,
        target: edge.target,
        relation: edge.relation,
        weight: edge.weight,
      }
    })

    // Create simulation
    const simulation = forceSimulation<SimNode>(simNodes)
      .force(
        'link',
        forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance(120)
      )
      .force('charge', forceManyBody().strength(-200))
      .force('center', forceCenter(0, 0))
      .alphaMin(0.01)

    simulationRef.current = simulation

    simulation.on('tick', () => {
      // Update nodes
      const updatedFlowNodes: Node[] = simNodes.map((n) => {
        return {
          id: n.id,
          type: 'circleNode',
          position: { x: n.x ?? 0, y: n.y ?? 0 },
          data: {
            label: n.label,
            type: n.type,
            degree: n.degree,
            isDimmed:
              (focusNodeIds.size > 0 && !focusNodeIds.has(n.id)) ||
              (hoveredNodeId !== null && !connectedNodeIds.has(n.id)),
          },
        }
      })

      // Update edges
      const updatedFlowEdges: Edge[] = filteredEdges.map((edge, index) => {
        const id = edgeId(edge, index)
        const isFocused = Boolean(graphFocus?.edgeId && id === graphFocus?.edgeId)
        const isDimmedEdge = hoveredNodeId !== null && edge.source !== hoveredNodeId && edge.target !== hoveredNodeId
        const width = clamp(1 + Math.log2(Math.max(1, edge.weight ?? 1)), 1.4, 5)

        const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
        const dimmedStroke = isDark ? '#1e293b' : '#e2e8f0'

        return {
          id,
          source: edge.source,
          target: edge.target,
          label: edge.relation?.slice(0, 28),
          animated: isFocused,
          style: {
            stroke: isFocused ? '#10b981' : isDimmedEdge ? dimmedStroke : '#94a3b8',
            strokeWidth: isFocused ? width + 1.5 : width,
            opacity: isDimmedEdge ? 0.2 : 1,
          },
          labelBgPadding: [6, 3],
          labelBgBorderRadius: 5,
          labelStyle: {
            fontSize: 9,
            fill: isFocused ? '#047857' : '#475569',
            fontWeight: 700,
            opacity: isDimmedEdge ? 0.2 : 1
          },
        }
      })

      setNodes(updatedFlowNodes)
      setEdges(updatedFlowEdges)
    })

    return () => {
      simulation.stop()
      simulationRef.current = null
    }
  }, [filteredNodes, filteredEdges, graphFocus, hoveredNodeId, connectedNodeIds, setNodes, setEdges])

  useEffect(() => {
    if (!graphFocus || !data) return
    if (graphFocus.edgeId && edgeById.has(graphFocus.edgeId)) {
      setSelection({ kind: 'edge', id: graphFocus.edgeId })
      return
    }

    const nodeId = graphFocus.nodeIds.find((id) => nodeById.has(id))
    setSelection(nodeId ? { kind: 'node', id: nodeId } : null)
  }, [data, edgeById, graphFocus, nodeById])

  const handleSelectionChange = useCallback((params: OnSelectionChangeParams) => {
    const edge = params.edges[0]
    if (edge) {
      setSelection({ kind: 'edge', id: edge.id })
      return
    }

    const node = params.nodes[0]
    setSelection(node ? { kind: 'node', id: node.id } : null)
  }, [])

  const handleToggleType = useCallback((type: string) => {
    setSelectedTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) {
        next.delete(type)
      } else {
        next.add(type)
      }
      return next
    })
  }, [])

  const handleSelectAll = useCallback(() => {
    setSelectedTypes(new Set(availableTypes))
  }, [availableTypes])

  const handleClearAll = useCallback(() => {
    setSelectedTypes(new Set())
  }, [])

  const onNodeMouseEnter = useCallback((_event: React.MouseEvent, node: Node) => {
    setHoveredNodeId(node.id)
  }, [])

  const onNodeMouseLeave = useCallback((_event: React.MouseEvent, _node: Node) => {
    setHoveredNodeId(null)
  }, [])

  const onNodeDragStart = useCallback((_event: React.MouseEvent, node: Node) => {
    if (simulationRef.current) {
      simulationRef.current.alphaTarget(0.3).restart()
      const simNode = simulationRef.current.nodes().find((n: any) => n.id === node.id)
      if (simNode) {
        simNode.fx = node.position.x
        simNode.fy = node.position.y
      }
    }
  }, [])

  const onNodeDrag = useCallback((_event: React.MouseEvent, node: Node) => {
    if (simulationRef.current) {
      const simNode = simulationRef.current.nodes().find((n: any) => n.id === node.id)
      if (simNode) {
        simNode.fx = node.position.x
        simNode.fy = node.position.y
      }
    }
  }, [])

  const onNodeDragStop = useCallback((_event: React.MouseEvent, node: Node) => {
    if (simulationRef.current) {
      simulationRef.current.alphaTarget(0)
      const simNode = simulationRef.current.nodes().find((n: any) => n.id === node.id)
      if (simNode) {
        simNode.fx = null
        simNode.fy = null
      }
    }
  }, [])

  if (isLoading) return <KGSkeleton />
  if (isError) return <ErrorState message={error instanceof Error ? error.message : undefined} />
  if (!data?.nodes?.length) return <EmptyState />

  return (
    <div className="relative h-full min-h-0 bg-background">
      <button
        onClick={() => setIsFilterOpen(true)}
        className="absolute left-3 top-3 z-10 flex items-center gap-2 rounded-xl border border-border/80 bg-background/90 px-3 py-2 text-xs font-bold text-foreground shadow-lg backdrop-blur hover:bg-accent transition-all active:scale-95 cursor-pointer animate-in fade-in duration-300"
      >
        <Filter size={14} className="text-emerald-600 dark:text-emerald-400" />
        Bộ lọc thực thể
      </button>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onSelectionChange={handleSelectionChange}
        onNodeDragStart={onNodeDragStart}
        onNodeDrag={onNodeDrag}
        onNodeDragStop={onNodeDragStop}
        onNodeMouseEnter={onNodeMouseEnter}
        onNodeMouseLeave={onNodeMouseLeave}
        fitView
        fitViewOptions={{ padding: 0.22 }}
        minZoom={0.25}
        maxZoom={1.8}
        proOptions={{ hideAttribution: true }}
        className={cn('h-full text-xs')}
      >
        <Background gap={18} color="#e2e8f0" />
        <Controls />
      </ReactFlow>

      <DetailPanel node={selectedNode} edge={selectedEdge} />

      {isFilterOpen && (
        <GraphFilter
          availableTypes={availableTypes}
          selectedTypes={selectedTypes}
          onToggleType={handleToggleType}
          onSelectAll={handleSelectAll}
          onClearAll={handleClearAll}
          onClose={() => setIsFilterOpen(false)}
        />
      )}
    </div>
  )
}
