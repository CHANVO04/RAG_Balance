import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import {
  Activity,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock3,
  Database,
  DollarSign,
  FileText,
  GitBranch,
  HardDrive,
  Image as ImageIcon,
  Layers3,
  Network,
} from 'lucide-react'
import { fetchDocuments, fetchGraph, fetchUMAP, fetchVectorChunks, type UMAPPoint, type VectorChunk } from '../../api/query'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { SourceInfo, useStore, type DocumentInfo } from '../../store'
import { Skeleton } from '../ui/Skeleton'
import { useToastStore } from '../../store/toastStore'

const NOT_RECORDED = <span className="text-sm font-bold text-muted-foreground">Not recorded</span>

const MetricCard = ({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string
  value: ReactNode
  detail?: ReactNode
  icon: typeof FileText
}) => (
  <div className="rounded-2xl border border-border/50 bg-card p-4 shadow-sm">
    <div className="mb-3 flex items-center justify-between gap-2">
      <div className="rounded-xl bg-primary/10 p-2 text-primary">
        <Icon size={18} />
      </div>
      <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{label}</span>
    </div>
    <div className="text-2xl font-bold">{value}</div>
    {detail && <p className="mt-1 text-[10px] font-semibold leading-relaxed text-muted-foreground">{detail}</p>}
  </div>
)

function modeLabel(strategy?: string) {
  if (strategy === 'only_vector_fast') return 'Fast Vector'
  if (strategy === 'hybrid') return 'Hybrid Graph + Vector'
  return 'Vector + Visuals'
}

function modeDescription(strategy?: string) {
  if (strategy === 'only_vector_fast') return 'Text/table chunks only. Visual payloads and graph extraction are skipped.'
  if (strategy === 'hybrid') return 'Vector chunks with visual evidence and Neo4j graph relationships.'
  return 'Vector chunks with optional table, image, and formula visual evidence.'
}

function sourceFromChunk(chunk: VectorChunk): SourceInfo {
  const kind = chunk.has_table ? 'table' : chunk.has_image ? 'image' : chunk.has_formula ? 'formula' : 'text'
  return {
    id: Math.max(1, chunk.chunk_index + 1),
    citation_id: `C${chunk.chunk_index}`,
    ref_id: `chunk-${chunk.chunk_index}`,
    kind,
    content: chunk.content,
    file_name: chunk.file_name,
    page: Math.max(1, chunk.page || 1),
    score: 1,
    section_label: chunk.section_label,
    has_table: chunk.has_table,
    has_formula: chunk.has_formula,
    has_image: chunk.has_image,
    pdf_url: '',
    display: chunk.content,
  }
}

function compactText(text: string, limit = 180) {
  const normalized = text.replace(/\s+/g, ' ').trim()
  return normalized.length > limit ? `${normalized.slice(0, limit)}...` : normalized
}

function formatDuration(seconds?: number | null) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return null
  if (seconds < 60) return `${seconds.toFixed(2)}s`
  const minutes = Math.floor(seconds / 60)
  const remaining = Math.round(seconds % 60)
  return `${minutes}m ${remaining}s`
}

function formatTokens(tokens?: number | null) {
  if (typeof tokens !== 'number' || !Number.isFinite(tokens)) return null
  return Math.max(0, Math.round(tokens)).toLocaleString()
}

function formatUsd(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 6, maximumFractionDigits: 8 })}`
}

function hasTiming(doc: DocumentInfo) {
  return typeof doc.processing_time_seconds === 'number' && Number.isFinite(doc.processing_time_seconds)
}

function hasEmbeddingMetrics(doc: DocumentInfo) {
  return typeof doc.embedding?.input_tokens === 'number' && Number.isFinite(doc.embedding.input_tokens)
}

function stageLabel(stage: string) {
  const labels: Record<string, string> = {
    parse_layout: 'Parse layout',
    visual_analysis: 'Visual analysis',
    chunk: 'Chunking',
    dedup: 'Dedup',
    embedding: 'Embedding',
    qdrant_docs_upsert: 'Qdrant docs',
    qdrant_visuals_upsert: 'Visual payloads',
    qdrant_visuals_upsert_skipped: 'Visual payloads skipped',
    kg_extract: 'Graph extraction',
    registry_store: 'Registry store',
  }
  return labels[stage] ?? stage.replace(/_/g, ' ')
}

type ModeKind = 'fast' | 'visual' | 'hybrid'
type PipelineState = 'enabled' | 'skipped'

interface PipelineStep {
  label: string
  detail: string
  state: PipelineState
  stageKey?: string
}

function modeKind(strategy?: string): ModeKind {
  if (strategy === 'only_vector_fast') return 'fast'
  if (strategy === 'hybrid') return 'hybrid'
  return 'visual'
}

function pipelineSteps(kind: ModeKind): PipelineStep[] {
  const base: PipelineStep[] = [
    { label: 'Parse PDF layout', detail: 'Docling extracts text, tables, pages, and layout structure.', state: 'enabled', stageKey: 'parse_layout' },
    { label: 'Chunk text/table', detail: 'Text and readable table content become retrieval chunks.', state: 'enabled', stageKey: 'chunk' },
    { label: 'Embedding', detail: 'Chunks are embedded with the configured OpenAI embedding model.', state: 'enabled', stageKey: 'embedding' },
    { label: 'Qdrant rag_docs', detail: 'Dense vectors and chunk payloads are stored for retrieval.', state: 'enabled', stageKey: 'qdrant_docs_upsert' },
  ]

  if (kind === 'fast') {
    return [
      ...base,
      { label: 'Visual analysis', detail: 'Skipped by Fast mode to reduce time, cost, and storage.', state: 'skipped' },
      { label: 'Qdrant rag_visuals', detail: 'Skipped by Fast mode; no high-detail visual payload is stored.', state: 'skipped' },
      { label: 'KG extraction', detail: 'Skipped by Fast mode.', state: 'skipped' },
      { label: 'Neo4j storage', detail: 'Skipped by Fast mode.', state: 'skipped' },
    ]
  }

  const visualSteps: PipelineStep[] = [
    { label: 'Visual analysis', detail: 'Tables, figures, and formulas can be analyzed as visual evidence.', state: 'enabled', stageKey: 'visual_analysis' },
    { label: 'Qdrant rag_visuals', detail: 'High-detail visual payloads are stored for visual/table/formula QA.', state: 'enabled', stageKey: 'qdrant_visuals_upsert' },
  ]

  if (kind === 'visual') {
    return [
      base[0],
      ...visualSteps,
      ...base.slice(1),
      { label: 'KG extraction', detail: 'Skipped by Vector + Visual mode.', state: 'skipped' },
      { label: 'Neo4j storage', detail: 'Skipped by Vector + Visual mode.', state: 'skipped' },
    ]
  }

  return [
    base[0],
    ...visualSteps,
    ...base.slice(1),
    { label: 'KG extraction', detail: 'Entities and relations are extracted for graph retrieval.', state: 'enabled', stageKey: 'kg_extract' },
    { label: 'Neo4j storage', detail: 'Graph entities and relationships are stored for multi-hop context.', state: 'enabled' },
  ]
}

function modeTradeoff(kind: ModeKind) {
  if (kind === 'fast') {
    return {
      title: 'Fast Vector trade-off',
      body: 'Best for text-heavy papers and quick demos. It should be the fastest and cheapest mode, but it is intentionally weaker for figure, formula, and image questions.',
    }
  }
  if (kind === 'hybrid') {
    return {
      title: 'Hybrid trade-off',
      body: 'Most complete ingest path. It adds visual evidence and graph extraction, so it is strongest for relation-heavy or multi-hop questions but has the highest time and cost.',
    }
  }
  return {
    title: 'Vector + Visual trade-off',
    body: 'Better for scientific papers with tables, figures, and formulas. It costs more than Fast because it stores visual evidence, but it skips graph extraction.',
  }
}

function stepBadge(step: PipelineStep, selectedDoc: DocumentInfo | null) {
  if (step.state === 'skipped') return 'Skipped by mode'
  const seconds = step.stageKey ? selectedDoc?.stage_timings?.[step.stageKey] : undefined
  return formatDuration(seconds) ?? 'Enabled by mode'
}

function stepBadgeClass(step: PipelineStep, selectedDoc: DocumentInfo | null) {
  if (step.state === 'skipped') return 'border-border bg-muted text-muted-foreground'
  const hasRecordedTime = step.stageKey && typeof selectedDoc?.stage_timings?.[step.stageKey] === 'number'
  return hasRecordedTime
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : 'border-primary/20 bg-primary/10 text-primary'
}

function PipelineTimeline({ kind, selectedDoc }: { kind: ModeKind; selectedDoc: DocumentInfo | null }) {
  return (
    <div className="rounded-2xl border border-border/50 bg-card p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold uppercase text-muted-foreground">Pipeline Timeline</h3>
          <p className="mt-1 text-[10px] text-muted-foreground">Mode stages are explicit; recorded timing appears when available for the selected file.</p>
        </div>
        <Activity size={18} className="text-primary" />
      </div>
      <div className="space-y-2">
        {pipelineSteps(kind).map((step, index) => (
          <div key={`${step.label}-${index}`} className="rounded-xl border border-border/50 bg-muted/20 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-xs font-bold">{index + 1}. {step.label}</div>
                <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">{step.detail}</p>
              </div>
              <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-black uppercase ${stepBadgeClass(step, selectedDoc)}`}>
                {stepBadge(step, selectedDoc)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function StorageFootprint({
  kind,
  ragDocs,
  visualSignals,
  graphNodes,
  graphEdges,
  graphLoading,
  graphError,
}: {
  kind: ModeKind
  ragDocs: number
  visualSignals: number
  graphNodes: number
  graphEdges: number
  graphLoading: boolean
  graphError: boolean
}) {
  const visualValue = kind === 'fast' ? 'Skipped' : 'Enabled'
  const visualDetail = kind === 'fast'
    ? 'Fast mode should not write high-detail visual payloads.'
    : visualSignals > 0
      ? `${visualSignals} detected table/image/formula signals from registry.`
      : 'Enabled by mode; no persisted visual count for this selection.'
  const graphValue = kind === 'hybrid'
    ? graphLoading
      ? 'Loading'
      : graphError
        ? 'Unavailable'
        : `${graphNodes}/${graphEdges}`
    : 'Skipped'
  const graphDetail = kind === 'hybrid'
    ? graphError
      ? 'Graph API could not be loaded.'
      : 'Neo4j nodes / relations visible from Graph API.'
    : 'Graph storage is skipped by this mode.'

  return (
    <div className="rounded-2xl border border-border/50 bg-card p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold uppercase text-muted-foreground">Storage Footprint</h3>
          <p className="mt-1 text-[10px] text-muted-foreground">Shows where this mode stores retrieval evidence.</p>
        </div>
        <HardDrive size={18} className="text-primary" />
      </div>
      <div className="grid gap-3 lg:grid-cols-3">
        <MetricCard label="rag_docs" value={ragDocs} detail="Qdrant dense text chunks." icon={Database} />
        <MetricCard label="rag_visuals" value={visualValue} detail={visualDetail} icon={ImageIcon} />
        <MetricCard label="Neo4j" value={graphValue} detail={graphDetail} icon={GitBranch} />
      </div>
    </div>
  )
}

function ModeTradeoffCard({ kind }: { kind: ModeKind }) {
  const tradeoff = modeTradeoff(kind)
  return (
    <div className="rounded-2xl border border-border/50 bg-card p-4">
      <div className="mb-2 flex items-center gap-2">
        <Network size={16} className="text-primary" />
        <h3 className="text-xs font-bold uppercase text-muted-foreground">Mode Capability</h3>
      </div>
      <div className="text-sm font-black">{tradeoff.title}</div>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{tradeoff.body}</p>
    </div>
  )
}

function ModeComparison({ kind }: { kind: ModeKind }) {
  const columns: Array<{ key: ModeKind; label: string }> = [
    { key: 'fast', label: 'Fast' },
    { key: 'visual', label: 'Vector + Visual' },
    { key: 'hybrid', label: 'Hybrid' },
  ]
  const rows = [
    ['Text chunks', 'Yes', 'Yes', 'Yes'],
    ['Table text', 'Basic text/table markdown', 'Text + visual evidence', 'Text + visual evidence'],
    ['Image/Figure analysis', 'Skipped', 'Enabled', 'Enabled'],
    ['Formula visual analysis', 'Skipped', 'Enabled', 'Enabled'],
    ['rag_docs', 'Enabled', 'Enabled', 'Enabled'],
    ['rag_visuals', 'Skipped', 'Enabled', 'Enabled'],
    ['KG extraction', 'Skipped', 'Skipped', 'Enabled'],
    ['Neo4j storage', 'Skipped', 'Skipped', 'Enabled'],
    ['Cost profile', 'Lowest', 'Medium', 'Highest'],
    ['Best use case', 'Text-heavy papers', 'Visual/table/formula papers', 'Relation and multi-hop papers'],
  ]

  return (
    <div className="rounded-2xl border border-border/50 bg-card p-4">
      <div className="mb-4">
        <h3 className="text-xs font-bold uppercase text-muted-foreground">Mode Comparison</h3>
        <p className="mt-1 text-[10px] text-muted-foreground">The active mode column is highlighted so the ingest trade-off is visible at a glance.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] border-separate border-spacing-0 text-left text-[10px]">
          <thead>
            <tr>
              <th className="rounded-l-xl bg-muted/40 px-3 py-2 font-black uppercase text-muted-foreground">Capability</th>
              {columns.map((column, index) => (
                <th
                  key={column.key}
                  className={`px-3 py-2 font-black uppercase ${kind === column.key ? 'bg-primary/10 text-primary' : 'bg-muted/40 text-muted-foreground'} ${index === columns.length - 1 ? 'rounded-r-xl' : ''}`}
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row[0]}>
                <td className="border-b border-border/40 px-3 py-2 font-bold text-foreground">{row[0]}</td>
                {columns.map((column, index) => (
                  <td
                    key={column.key}
                    className={`border-b border-border/40 px-3 py-2 leading-relaxed ${kind === column.key ? 'bg-primary/5 font-bold text-foreground' : 'text-muted-foreground'} ${index === columns.length - 1 ? 'rounded-r-lg' : ''}`}
                  >
                    {row[index + 1]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function VectorTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: UMAPPoint }> }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  return (
    <div className="max-w-56 rounded-xl border border-border bg-card p-2 text-[10px] shadow-lg">
      <div className="truncate font-bold">{point.file_name}</div>
      <div className="mt-1 text-muted-foreground">{point.label || point.chunk_id}</div>
    </div>
  )
}

export default function AnalyticsDashboard() {
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const activeWorkspace = useWorkspaceStore((s) => s.workspaces.find((workspace) => workspace.id === s.activeWorkspaceId))
  const activateSource = useStore((s) => s.activateSource)
  const pushToast = useToastStore((s) => s.pushToast)
  const [selectedFile, setSelectedFile] = useState('summary')
  const [showChunks, setShowChunks] = useState(true)
  const [expandedChunkId, setExpandedChunkId] = useState<string | null>(null)

  const docsQuery = useQuery({
    queryKey: ['documents', activeWorkspaceId],
    queryFn: () => fetchDocuments(activeWorkspaceId),
  })
  const chunksQuery = useQuery({
    queryKey: ['vector-chunks', activeWorkspaceId],
    queryFn: () => fetchVectorChunks(activeWorkspaceId, 1000),
    staleTime: 300_000,
  })
  const umapQuery = useQuery({
    queryKey: ['umap', activeWorkspaceId],
    queryFn: () => fetchUMAP(activeWorkspaceId),
    staleTime: 300_000,
    retry: 1,
  })

  const docs = docsQuery.data ?? []
  const chunks = chunksQuery.data ?? []
  const strategy = activeWorkspace?.strategy ?? 'only_vector_multimodal'
  const kind = modeKind(strategy)
  const isFastMode = strategy === 'only_vector_fast'
  const fileNames = useMemo(() => docs.map((doc) => doc.file_name).sort(), [docs])

  const graphQuery = useQuery({
    queryKey: ['graph', activeWorkspaceId, false],
    queryFn: () => fetchGraph(activeWorkspaceId, false),
    enabled: kind === 'hybrid',
    staleTime: 300_000,
    retry: 1,
  })

  useEffect(() => {
    if (selectedFile !== 'summary' && !fileNames.includes(selectedFile)) {
      setSelectedFile('summary')
    }
  }, [fileNames, selectedFile])

  useEffect(() => {
    if (docsQuery.isError || chunksQuery.isError || umapQuery.isError || graphQuery.isError) {
      pushToast({ type: 'error', title: 'Ingest information unavailable', description: 'Some ingest data could not be loaded.' })
    }
  }, [chunksQuery.isError, docsQuery.isError, graphQuery.isError, pushToast, umapQuery.isError])

  const visibleDocs = useMemo(() => {
    if (selectedFile === 'summary') return docs
    return docs.filter((doc) => doc.file_name === selectedFile)
  }, [docs, selectedFile])

  const visibleChunks = useMemo(() => {
    const filtered = selectedFile === 'summary'
      ? chunks
      : chunks.filter((chunk) => chunk.file_name === selectedFile)
    return [...filtered].sort((a, b) =>
      a.file_name.localeCompare(b.file_name) || a.chunk_index - b.chunk_index,
    )
  }, [chunks, selectedFile])

  const visibleMapData = useMemo(() => {
    const visibleIds = new Set(visibleChunks.map((chunk) => chunk.chunk_id))
    return (umapQuery.data ?? []).filter((point) => visibleIds.has(point.chunk_id))
  }, [umapQuery.data, visibleChunks])

  const selectedDoc = selectedFile === 'summary' ? null : visibleDocs[0]
  const recordedTimingDocs = visibleDocs.filter(hasTiming)
  const recordedEmbeddingDocs = visibleDocs.filter(hasEmbeddingMetrics)
  const hasMissingTiming = visibleDocs.some((doc) => !hasTiming(doc))
  const hasMissingEmbedding = visibleDocs.some((doc) => !hasEmbeddingMetrics(doc))

  const totalChunks = visibleDocs.reduce((sum, doc) => sum + (doc.chunk_count || 0), 0)
  const totalProcessingSeconds = recordedTimingDocs.length
    ? recordedTimingDocs.reduce((sum, doc) => sum + (doc.processing_time_seconds ?? 0), 0)
    : null
  const totalEmbeddingTokens = recordedEmbeddingDocs.length
    ? recordedEmbeddingDocs.reduce((sum, doc) => sum + (doc.embedding?.input_tokens ?? 0), 0)
    : null
  const totalEmbeddingCost = recordedEmbeddingDocs.length
    ? recordedEmbeddingDocs.reduce((sum, doc) => sum + (doc.embedding?.cost_usd ?? 0), 0)
    : null
  const embeddingModels = Array.from(new Set(recordedEmbeddingDocs.map((doc) => doc.embedding?.model).filter(Boolean)))
  const stageTimings = selectedDoc?.stage_timings ?? {}
  const visualSignals = visibleDocs.reduce(
    (sum, doc) => sum + (doc.total_tables ?? 0) + (doc.total_images ?? 0) + (doc.total_formulas ?? 0),
    0,
  )
  const graphNodeCount = graphQuery.data?.nodes?.length ?? 0
  const graphEdgeCount = graphQuery.data?.edges?.length ?? 0

  if (docsQuery.isLoading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton variant="shimmer" className="h-5 w-40" />
        <Skeleton variant="shimmer" className="h-32 rounded-2xl" />
        <div className="grid grid-cols-2 gap-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} variant="shimmer" className="h-24 rounded-2xl" />)}
        </div>
      </div>
    )
  }

  return (
    <div className="h-full space-y-6 overflow-y-auto p-6 pb-20">
      <div className="flex items-center gap-2">
        <Activity size={18} className="text-primary" />
        <h2 className="text-sm font-bold uppercase tracking-wider">Ingest Information</h2>
      </div>

      <div className="rounded-2xl border border-primary/15 bg-primary/5 p-4">
        <div className="flex items-start gap-3">
          <div className="rounded-xl border border-border/60 bg-background p-2 text-primary">
            <Layers3 size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-xs font-black uppercase tracking-wider">{modeLabel(strategy)}</h3>
              <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[9px] font-black uppercase text-primary">
                {activeWorkspace?.name ?? activeWorkspaceId}
              </span>
            </div>
            <p className="mt-1 text-[10px] font-semibold leading-relaxed text-muted-foreground">
              {modeDescription(strategy)}
            </p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <div className="rounded-xl border border-border/50 bg-card/70 p-3">
            <div className="text-[9px] font-black uppercase tracking-wider text-muted-foreground">Mode Visual Flow</div>
            <div className="mt-1 flex items-center gap-1.5 text-xs font-bold">
              <CheckCircle2 size={13} className={isFastMode ? 'text-emerald-500' : 'text-primary'} />
              {isFastMode ? 'Skip visual storage' : 'Allow visual storage'}
            </div>
          </div>
          <div className="rounded-xl border border-border/50 bg-card/70 p-3">
            <div className="text-[9px] font-black uppercase tracking-wider text-muted-foreground">Mode Graph Flow</div>
            <div className="mt-1 flex items-center gap-1.5 text-xs font-bold">
              <CheckCircle2 size={13} className={strategy === 'hybrid' ? 'text-primary' : 'text-emerald-500'} />
              {strategy === 'hybrid' ? 'Allow KG extraction' : 'Skip KG extraction'}
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-border/50 bg-card p-4">
        <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground" htmlFor="ingest-file-filter">
          Inspect file
        </label>
        <select
          id="ingest-file-filter"
          value={selectedFile}
          onChange={(event) => setSelectedFile(event.target.value)}
          className="mt-2 w-full rounded-xl border border-border bg-background px-3 py-2 text-xs font-bold outline-none transition-colors focus:border-primary"
        >
          <option value="summary">Summary - all ingested files</option>
          {fileNames.map((fileName) => (
            <option key={fileName} value={fileName}>{fileName}</option>
          ))}
        </select>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
          Metrics below come from persisted ingest metadata. Older documents show Not recorded until they are ingested again.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <MetricCard label="Files" value={visibleDocs.length} detail={selectedFile === 'summary' ? 'All files in this workspace.' : selectedFile} icon={FileText} />
        <MetricCard label="Chunks" value={totalChunks} detail={`${visibleChunks.length} Qdrant chunks visible`} icon={BarChart3} />
        <MetricCard
          label="Ingest Time"
          value={formatDuration(totalProcessingSeconds) ?? NOT_RECORDED}
          detail={hasMissingTiming ? 'Some selected files have no persisted timing.' : 'Persisted backend processing time.'}
          icon={Clock3}
        />
        <MetricCard
          label="Embedding Cost"
          value={formatUsd(totalEmbeddingCost) ?? NOT_RECORDED}
          detail={formatTokens(totalEmbeddingTokens)
            ? `${formatTokens(totalEmbeddingTokens)} input tokens · ${embeddingModels.join(', ') || 'embedding model recorded'}`
            : hasMissingEmbedding
              ? 'Embedding usage was not recorded for this ingest.'
              : 'No embedding usage recorded.'}
          icon={DollarSign}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
        <PipelineTimeline kind={kind} selectedDoc={selectedDoc} />
        <ModeTradeoffCard kind={kind} />
      </div>

      <StorageFootprint
        kind={kind}
        ragDocs={visibleChunks.length}
        visualSignals={visualSignals}
        graphNodes={graphNodeCount}
        graphEdges={graphEdgeCount}
        graphLoading={graphQuery.isLoading}
        graphError={graphQuery.isError}
      />

      {selectedDoc && (
        <div className="rounded-2xl border border-border/50 bg-card p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-xs font-bold uppercase text-muted-foreground">Persisted Stage Timings</h3>
              <p className="mt-1 text-[10px] text-muted-foreground">{selectedDoc.file_name}</p>
            </div>
            <span className="text-[10px] font-bold text-muted-foreground">{Object.keys(stageTimings).length} stages</span>
          </div>
          {Object.keys(stageTimings).length ? (
            <div className="mt-4 space-y-2">
              {Object.entries(stageTimings).map(([stage, seconds]) => (
                <div key={stage} className="flex items-center justify-between gap-3 rounded-xl bg-muted/30 px-3 py-2 text-[10px] font-bold">
                  <span>{stageLabel(stage)}</span>
                  <span className="text-muted-foreground">{formatDuration(seconds) ?? NOT_RECORDED}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-xl bg-muted/30 p-3 text-xs text-muted-foreground">Not recorded for this ingest.</div>
          )}
        </div>
      )}

      <ModeComparison kind={kind} />

      <div className="rounded-2xl border border-border/50 bg-card p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold uppercase text-muted-foreground">Vector Map</h3>
            <p className="mt-1 text-[10px] text-muted-foreground">{visibleMapData.length} vector points for the current selection</p>
          </div>
          <Database size={18} className="text-primary" />
        </div>
        <div className="h-64 rounded-2xl bg-muted/20 p-2">
          {umapQuery.isLoading ? (
            <Skeleton variant="shimmer" className="h-full rounded-2xl" />
          ) : visibleMapData.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 12, right: 12, bottom: 12, left: 12 }}>
                <XAxis dataKey="x" type="number" hide domain={['dataMin - 0.1', 'dataMax + 0.1']} />
                <YAxis dataKey="y" type="number" hide domain={['dataMin - 0.1', 'dataMax + 0.1']} />
                <Tooltip cursor={false} content={<VectorTooltip />} />
                <Scatter data={visibleMapData}>
                  {visibleMapData.map((point) => (
                    <Cell key={point.chunk_id} fill={selectedFile === 'summary' ? '#94a3b8' : '#2563eb'} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
              No vector points for this selection.
            </div>
          )}
        </div>
      </div>

      <div className="space-y-4 border-t border-border/50 pt-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold uppercase text-muted-foreground">Ingested Qdrant Chunks</h3>
            <p className="mt-1 text-[10px] text-muted-foreground">{visibleChunks.length} chunks ordered by file and chunk index</p>
          </div>
          <button
            onClick={() => setShowChunks((value) => !value)}
            className="flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[10px] font-bold text-muted-foreground hover:text-foreground"
          >
            {showChunks ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {showChunks ? 'Hide' : 'Show'}
          </button>
        </div>

        {showChunks && (
          <div className="space-y-2">
            {chunksQuery.isLoading && <Skeleton variant="shimmer" className="h-24 rounded-2xl" />}
            {visibleChunks.map((chunk) => {
              const expanded = expandedChunkId === chunk.chunk_id
              return (
                <div key={chunk.chunk_id} className="rounded-xl border border-border/50 bg-card">
                  <button
                    onClick={() => setExpandedChunkId(expanded ? null : chunk.chunk_id)}
                    className="flex w-full items-center gap-3 p-3 text-left"
                  >
                    <div className="w-14 shrink-0 rounded-lg bg-primary/10 px-2 py-1 text-center text-[10px] font-bold text-primary">
                      #{chunk.chunk_index}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-semibold">Page {chunk.page || '-'} · {chunk.section_label || chunk.doc_type}</div>
                      <div className="mt-1 truncate text-[10px] text-muted-foreground">{compactText(chunk.content)}</div>
                      {selectedFile === 'summary' && <div className="mt-1 truncate text-[9px] font-bold text-muted-foreground">{chunk.file_name}</div>}
                    </div>
                    {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                  {expanded && (
                    <div className="border-t border-border/50 p-3">
                      <div className="whitespace-pre-wrap rounded-xl bg-muted/30 p-3 text-xs leading-relaxed text-foreground/85">{chunk.content}</div>
                      <button
                        onClick={() => activateSource(sourceFromChunk(chunk))}
                        className="mt-3 rounded-full border border-border px-3 py-1.5 text-[10px] font-bold text-muted-foreground hover:border-primary hover:text-primary"
                      >
                        Open source
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
            {!chunksQuery.isLoading && visibleChunks.length === 0 && (
              <div className="rounded-2xl border border-border/50 bg-card p-4 text-xs text-muted-foreground">
                No chunks found for this selection.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
