import { useEffect, useMemo, useState } from 'react'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { useQuery } from '@tanstack/react-query'
import { Database, ExternalLink, FileText, Image, Maximize2, Minimize2, Search, Sigma, Table2 } from 'lucide-react'
import { fetchUMAP, fetchVectorChunks, UMAPPoint, VectorChunk } from '../../api/query'
import { UMAPSkeleton, Skeleton } from '../ui/Skeleton'
import { SourceInfo, useStore } from '../../store'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { useToastStore } from '../../store/toastStore'
import { cn } from '../../lib/utils'

type ChunkKind = 'text' | 'table' | 'image' | 'formula'

interface TraceSource {
  rank?: number
  citation_id?: string
  chunk_id?: string
  file_name?: string
  page?: number
  score?: number
  selection_reason?: string
  preview?: string
}

interface RetrievalTrace {
  question?: string
  settings?: {
    qdrant_limit?: number
    score_threshold?: number
    min_chunks?: number
    max_chunks?: number
    kg_mode?: string
    use_visuals?: boolean
  }
  counts?: {
    raw_docs?: number
    passed_threshold?: number
    final_context?: number
    filtered_out?: number
    kg_sources?: number
    graph_relationships_used_in_prompt?: number
  }
  context_used?: {
    kg?: boolean
    visual?: boolean
    document_inventory?: boolean
  }
  selection?: {
    fallback_used?: boolean
    selected_sources?: TraceSource[]
    filtered_out_sources?: TraceSource[]
  }
  prompt?: {
    system_prompt?: string
    user_prompt?: string
    custom_system_instruction?: string
    user_prompt_template?: string
  }
  sources?: TraceSource[]
}

const KIND_FILTERS: Array<{ id: 'all' | ChunkKind; label: string; Icon: typeof FileText }> = [
  { id: 'all', label: 'All', Icon: Database },
  { id: 'text', label: 'Text', Icon: FileText },
  { id: 'table', label: 'Tables', Icon: Table2 },
  { id: 'image', label: 'Images', Icon: Image },
  { id: 'formula', label: 'Formula', Icon: Sigma },
]

function chunkKind(chunk: VectorChunk): ChunkKind {
  const docType = chunk.doc_type.toLowerCase()
  if (chunk.has_table || docType.includes('table')) return 'table'
  if (chunk.has_image || docType.includes('image')) return 'image'
  if (chunk.has_formula || docType.includes('formula')) return 'formula'
  return 'text'
}

function chunkKey(chunk: Pick<VectorChunk, 'file_name' | 'page'>) {
  return `${chunk.file_name}::${chunk.page}`
}

function sourceFromChunk(chunk: VectorChunk): SourceInfo {
  return {
    id: Math.max(1, chunk.chunk_index + 1),
    citation_id: `C${chunk.chunk_index}`,
    ref_id: `chunk-${chunk.chunk_index}`,
    kind: chunkKind(chunk),
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

function compactText(text: string, limit = 240) {
  const normalized = text.replace(/\s+/g, ' ').trim()
  return normalized.length > limit ? `${normalized.slice(0, limit)}...` : normalized
}

function asRetrievalTrace(value: Record<string, unknown> | undefined): RetrievalTrace | null {
  if (!value || typeof value !== 'object') return null
  return value as RetrievalTrace
}

function formatScore(score?: number) {
  return typeof score === 'number' && Number.isFinite(score) ? score.toFixed(3) : '-'
}

function KindBadge({ kind }: { kind: ChunkKind }) {
  const styles = {
    text: 'bg-slate-500/10 text-slate-600 dark:text-slate-300',
    table: 'bg-blue-500/10 text-blue-600 dark:text-blue-300',
    image: 'bg-purple-500/10 text-purple-600 dark:text-purple-300',
    formula: 'bg-amber-500/10 text-amber-600 dark:text-amber-300',
  }
  return <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-bold uppercase', styles[kind])}>{kind}</span>
}

export default function UMAPSpace() {
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const messages = useStore((s) => s.messages)
  const activateSource = useStore((s) => s.activateSource)
  const pushToast = useToastStore((s) => s.pushToast)
  const [selectedFile, setSelectedFile] = useState('all')
  const [selectedKind, setSelectedKind] = useState<'all' | ChunkKind>('all')
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null)
  const [isExplorerExpanded, setExplorerExpanded] = useState(false)

  const chunksQuery = useQuery({
    queryKey: ['vector-chunks', activeWorkspaceId],
    queryFn: () => fetchVectorChunks(activeWorkspaceId, 500),
    staleTime: 300_000,
  })
  const umapQuery = useQuery({
    queryKey: ['umap', activeWorkspaceId],
    queryFn: () => fetchUMAP(activeWorkspaceId),
    staleTime: 300_000,
    retry: 1,
  })

  useEffect(() => {
    if (chunksQuery.isError) {
      pushToast({ type: 'error', title: 'Vector evidence unavailable', description: 'The chunk evidence list could not load.' })
    }
    if (umapQuery.isError) {
      pushToast({ type: 'error', title: 'Vector map unavailable', description: 'The semantic map could not load.' })
    }
  }, [chunksQuery.isError, pushToast, umapQuery.isError])

  const lastUserQuestion = useMemo(() => {
    return [...messages].reverse().find((message) => message.role === 'user')?.segments.map((s) => s.content).join(' ') ?? ''
  }, [messages])

  const lastAssistant = useMemo(() => {
    return [...messages].reverse().find((message) => message.role === 'assistant' && (message.retrievalTrace || message.sources?.length))
  }, [messages])
  const retrievalTrace = asRetrievalTrace(lastAssistant?.retrievalTrace)
  const traceSources = retrievalTrace?.sources ?? retrievalTrace?.selection?.selected_sources ?? []
  const usedChunkIds = useMemo(() => {
    return new Set(traceSources.map((source) => source.chunk_id).filter(Boolean) as string[])
  }, [traceSources])
  const retrievedKeys = useMemo(() => {
    return new Set((lastAssistant?.sources ?? []).map((source) => chunkKey(source)))
  }, [lastAssistant])
  const kgSources = lastAssistant?.kgSources ?? []

  const chunks = chunksQuery.data ?? []
  const chunksById = useMemo(() => {
    return chunks.reduce<Record<string, VectorChunk>>((acc, chunk) => {
      acc[chunk.chunk_id] = chunk
      return acc
    }, {})
  }, [chunks])
  const files = useMemo(() => Array.from(new Set(chunks.map((chunk) => chunk.file_name))).sort(), [chunks])
  const filteredChunks = useMemo(() => {
    const q = searchTerm.trim().toLowerCase()
    return chunks.filter((chunk) => {
      if (selectedFile !== 'all' && chunk.file_name !== selectedFile) return false
      if (selectedKind !== 'all' && chunkKind(chunk) !== selectedKind) return false
      if (!q) return true
      return `${chunk.file_name} ${chunk.section_label} ${chunk.content}`.toLowerCase().includes(q)
    })
  }, [chunks, searchTerm, selectedFile, selectedKind])

  const selectedChunk = useMemo(
    () => filteredChunks.find((chunk) => chunk.chunk_id === selectedChunkId) ?? filteredChunks[0],
    [filteredChunks, selectedChunkId],
  )

  const mapData = useMemo(() => {
    const visibleIds = new Set(filteredChunks.map((chunk) => chunk.chunk_id))
    return (umapQuery.data ?? []).filter((point) => visibleIds.has(point.chunk_id))
  }, [filteredChunks, umapQuery.data])

  const openChunk = (chunk: VectorChunk) => activateSource(sourceFromChunk(chunk))

  if (chunksQuery.isLoading) {
    return (
      <div className="h-full space-y-4">
        <div className="grid grid-cols-3 gap-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} variant="shimmer" className="h-16 rounded-xl" />)}
        </div>
        <UMAPSkeleton />
      </div>
    )
  }

  if (chunksQuery.isError) {
    return <div className="flex h-full items-center justify-center text-xs text-red-400">Failed to load vector evidence.</div>
  }

  if (!chunks.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center text-xs text-muted-foreground">
        <Database size={28} />
        <div>No vector chunks yet.</div>
      </div>
    )
  }

  return (
    <div className="flex min-h-full flex-col gap-4 pr-1 pb-16">
      <div className={cn('grid grid-cols-3 gap-3', isExplorerExpanded && 'hidden')}>
        <div className="rounded-xl border border-border/60 bg-card p-3">
          <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Chunks</div>
          <div className="mt-1 text-2xl font-bold">{chunks.length}</div>
        </div>
        <div className="rounded-xl border border-border/60 bg-card p-3">
          <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Files</div>
          <div className="mt-1 text-2xl font-bold">{files.length}</div>
        </div>
        <div className="rounded-xl border border-border/60 bg-card p-3">
          <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Retrieved</div>
          <div className="mt-1 text-2xl font-bold">{retrievalTrace?.counts?.final_context ?? usedChunkIds.size ?? retrievedKeys.size}</div>
        </div>
      </div>

      <div className={cn('rounded-2xl border border-border/60 bg-card p-3', isExplorerExpanded && 'hidden')}>
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <div className="text-xs font-bold">Context sent to LLM</div>
            <div className="max-w-[30rem] truncate text-[10px] text-muted-foreground">
              {retrievalTrace?.question || lastUserQuestion || 'Ask a question to inspect retrieval.'}
            </div>
          </div>
          {retrievalTrace ? (
            <span className={cn(
              'rounded-full px-2 py-1 text-[10px] font-bold',
              retrievalTrace.selection?.fallback_used ? 'bg-amber-500/10 text-amber-600' : 'bg-emerald-500/10 text-emerald-600',
            )}>
              {retrievalTrace.selection?.fallback_used ? 'fallback' : 'threshold'}
            </span>
          ) : null}
        </div>
        {retrievalTrace ? (
          <div className="space-y-3">
            <div className="grid grid-cols-4 gap-2">
              <div className="rounded-xl bg-muted/35 p-2">
                <div className="text-[9px] font-bold uppercase text-muted-foreground">Limit</div>
                <div className="text-sm font-black">{retrievalTrace.settings?.qdrant_limit ?? '-'}</div>
              </div>
              <div className="rounded-xl bg-muted/35 p-2">
                <div className="text-[9px] font-bold uppercase text-muted-foreground">Threshold</div>
                <div className="text-sm font-black">{formatScore(retrievalTrace.settings?.score_threshold)}</div>
              </div>
              <div className="rounded-xl bg-muted/35 p-2">
                <div className="text-[9px] font-bold uppercase text-muted-foreground">Passed</div>
                <div className="text-sm font-black">{retrievalTrace.counts?.passed_threshold ?? '-'}</div>
              </div>
              <div className="rounded-xl bg-muted/35 p-2">
                <div className="text-[9px] font-bold uppercase text-muted-foreground">Final</div>
                <div className="text-sm font-black">{retrievalTrace.counts?.final_context ?? '-'}/{retrievalTrace.settings?.max_chunks ?? 8}</div>
              </div>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              <div className="rounded-xl border border-border/60 p-2">
                <div className="mb-2 text-[10px] font-black uppercase text-muted-foreground">Chunks in prompt</div>
                <div className="max-h-40 space-y-2 overflow-y-auto pr-1">
                  {traceSources.length ? traceSources.map((source) => (
                    <button
                      key={`${source.chunk_id}-${source.rank}`}
                      onClick={() => source.chunk_id && setSelectedChunkId(source.chunk_id)}
                      className="block w-full rounded-lg bg-primary/5 p-2 text-left hover:bg-primary/10"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-[11px] font-bold">#{source.rank ?? '-'} {source.citation_id ? `[${source.citation_id}]` : ''}</span>
                        <span className="text-[10px] font-bold text-primary">{formatScore(source.score)}</span>
                      </div>
                      <div className="mt-0.5 truncate text-[10px] text-muted-foreground">{source.file_name} · p.{source.page || '-'}</div>
                      <div className="mt-1 line-clamp-2 text-[10px] leading-relaxed">{source.preview}</div>
                    </button>
                  )) : (
                    <div className="text-[10px] text-muted-foreground">No trace sources yet.</div>
                  )}
                </div>
              </div>
              <div className="rounded-xl border border-border/60 p-2">
                <div className="mb-2 text-[10px] font-black uppercase text-muted-foreground">Graph context</div>
                <div className="max-h-40 space-y-2 overflow-y-auto pr-1">
                  {kgSources.length ? kgSources.map((kg) => (
                    <div key={kg.id} className="rounded-lg bg-emerald-500/5 p-2">
                      <div className="text-[10px] font-black text-emerald-600">{kg.id}</div>
                      <div className="mt-0.5 text-[10px] leading-relaxed">
                        {kg.subject} --{kg.relation}--&gt; {kg.object}
                      </div>
                      <div className="mt-1 truncate text-[10px] text-muted-foreground">
                        {kg.source_file || 'KG metadata'} · p.{kg.page || '-'} · {kg.chunk_id || 'no chunk'}
                      </div>
                    </div>
                  )) : (
                    <div className="text-[10px] text-muted-foreground">
                      {retrievalTrace.context_used?.kg ? 'Graph context was used, but no citation metadata was returned.' : 'No graph context sent for this answer.'}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="rounded-xl bg-muted/30 p-3 text-xs text-muted-foreground">
            Ask a question, then this panel will show the exact chunks and graph evidence sent to the LLM.
          </div>
        )}
      </div>

      <div className={cn('rounded-2xl border border-border/60 bg-card p-3', isExplorerExpanded && 'hidden')}>
        <div className="mb-2">
          <div className="text-xs font-bold">Prompt sent to LLM</div>
          <div className="text-[10px] text-muted-foreground">
            Shows the actual system and user prompts returned by the backend after a query.
          </div>
        </div>
        {retrievalTrace?.prompt?.system_prompt || retrievalTrace?.prompt?.user_prompt ? (
          <div className="space-y-2">
            <details className="rounded-xl border border-border/60 bg-muted/20 p-2">
              <summary className="cursor-pointer text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                System prompt
              </summary>
              <pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-background/80 p-2 text-[10px] leading-relaxed text-foreground/80">
                {retrievalTrace.prompt.system_prompt}
              </pre>
            </details>
            <details className="rounded-xl border border-border/60 bg-muted/20 p-2">
              <summary className="cursor-pointer text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                User prompt
              </summary>
              <pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-background/80 p-2 text-[10px] leading-relaxed text-foreground/80">
                {retrievalTrace.prompt.user_prompt}
              </pre>
            </details>
          </div>
        ) : (
          <div className="rounded-xl bg-muted/30 p-3 text-xs text-muted-foreground">
            Ask a question to see the exact prompts used for generation.
          </div>
        )}
      </div>

      <div className={cn('rounded-2xl border border-border/60 bg-card p-3', isExplorerExpanded && 'hidden')}>
        <div className="mb-2 flex items-center justify-between gap-3">
          <div>
            <div className="text-xs font-bold">Retrieval Map</div>
            <div className="max-w-[26rem] truncate text-[10px] text-muted-foreground">{lastUserQuestion || 'No active question yet'}</div>
          </div>
          <span className="rounded-full bg-primary/10 px-2 py-1 text-[10px] font-bold text-primary">{mapData.length} points</span>
        </div>
        <div className="h-52 overflow-hidden rounded-xl bg-muted/20">
          {umapQuery.isLoading ? (
            <UMAPSkeleton />
          ) : umapQuery.isError || !mapData.length ? (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground">Semantic map is not available for this filter.</div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 12, right: 12, bottom: 12, left: 12 }}>
                <XAxis dataKey="x" type="number" domain={['auto', 'auto']} hide />
                <YAxis dataKey="y" type="number" domain={['auto', 'auto']} hide />
                <Tooltip
                  cursor={{ strokeDasharray: '3 3' }}
                  content={({ payload }) => {
                    const point = payload?.[0]?.payload as UMAPPoint | undefined
                    if (!point) return null
                    const chunk = chunksById[point.chunk_id]
                    return (
                      <div className="max-h-80 w-[min(34rem,calc(100vw-4rem))] overflow-y-auto rounded-xl border border-border bg-card p-3 text-xs shadow-xl">
                        <div className="font-semibold">{point.file_name}</div>
                        <div className="mt-1 text-[10px] font-semibold text-muted-foreground">
                          Chunk {chunk?.chunk_index ?? '-'} · page {chunk?.page || '-'} · {chunkKind(chunk ?? {
                            chunk_id: point.chunk_id,
                            file_name: point.file_name,
                            chunk_index: 0,
                            page: 0,
                            section_label: '',
                            doc_type: 'text',
                            content: point.label,
                            has_table: false,
                            has_formula: false,
                            has_image: false,
                          })}
                        </div>
                        <div className="mt-2 whitespace-pre-wrap break-words leading-relaxed text-foreground/85">
                          {chunk?.content || point.label}
                        </div>
                      </div>
                    )
                  }}
                />
                <Scatter data={mapData} onClick={(point: UMAPPoint) => setSelectedChunkId(point.chunk_id)}>
                  {mapData.map((point) => {
                    const isSelected = point.chunk_id === selectedChunk?.chunk_id
                    const isRetrieved = usedChunkIds.has(point.chunk_id)
                      || filteredChunks.some((chunk) => chunk.chunk_id === point.chunk_id && retrievedKeys.has(chunkKey(chunk)))
                    return <Cell key={point.chunk_id} fill={isSelected ? '#2563eb' : isRetrieved ? '#10b981' : '#94a3b8'} opacity={isSelected || isRetrieved ? 0.95 : 0.55} />
                  })}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Search chunks"
            className="h-9 w-full rounded-xl border border-border bg-card pl-9 pr-3 text-xs outline-none focus:border-primary"
          />
        </div>
        <select
          value={selectedFile}
          onChange={(event) => setSelectedFile(event.target.value)}
          className="h-9 max-w-44 rounded-xl border border-border bg-card px-3 text-xs outline-none focus:border-primary"
        >
          <option value="all">All files</option>
          {files.map((file) => <option key={file} value={file}>{file}</option>)}
        </select>
        <button
          onClick={() => setExplorerExpanded((value) => !value)}
          className="flex h-9 items-center gap-1.5 rounded-xl border border-border bg-card px-3 text-[10px] font-bold uppercase text-muted-foreground hover:border-primary hover:text-primary"
        >
          {isExplorerExpanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          {isExplorerExpanded ? 'Collapse' : 'Expand'}
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {KIND_FILTERS.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setSelectedKind(id)}
            className={cn(
              'flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[10px] font-bold uppercase transition-colors',
              selectedKind === id ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon size={12} />
            {label}
          </button>
        ))}
      </div>

      <div
        className={cn(
          'grid gap-3',
          isExplorerExpanded
            ? 'min-h-[620px] grid-cols-1'
            : 'min-h-[520px] grid-cols-[minmax(180px,0.9fr)_minmax(220px,1.1fr)]',
        )}
      >
        <div className="max-h-[640px] min-h-0 overflow-y-auto rounded-2xl border border-border/60 bg-card">
          {filteredChunks.map((chunk) => {
            const isSelected = selectedChunk?.chunk_id === chunk.chunk_id
            const isRetrieved = usedChunkIds.has(chunk.chunk_id) || retrievedKeys.has(chunkKey(chunk))
            return (
              <button
                key={chunk.chunk_id}
                onClick={() => setSelectedChunkId(chunk.chunk_id)}
                className={cn(
                  'block w-full border-b border-border/50 p-3 text-left transition-colors last:border-b-0',
                  isSelected ? 'bg-primary/10' : 'hover:bg-accent/60',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold">Chunk {chunk.chunk_index}</span>
                  {isRetrieved ? <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-600">used</span> : null}
                </div>
                <div className="mt-1 truncate text-[10px] text-muted-foreground">{chunk.file_name} · p.{chunk.page || '-'}</div>
                <div className={cn('mt-2 text-xs text-foreground/80', isExplorerExpanded ? 'line-clamp-3' : 'line-clamp-2')}>
                  {compactText(chunk.content, isExplorerExpanded ? 260 : 150)}
                </div>
              </button>
            )
          })}
        </div>

        <div className="max-h-[640px] min-h-0 overflow-y-auto rounded-2xl border border-border/60 bg-card p-4">
          {selectedChunk ? (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate text-sm font-bold">Chunk {selectedChunk.chunk_index}</h3>
                    <KindBadge kind={chunkKind(selectedChunk)} />
                  </div>
                  <div className="mt-1 text-[11px] text-muted-foreground">{selectedChunk.file_name} · page {selectedChunk.page || '-'}</div>
                </div>
                <button
                  onClick={() => openChunk(selectedChunk)}
                  className="flex shrink-0 items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-[10px] font-bold text-muted-foreground hover:border-primary hover:text-primary"
                >
                  <ExternalLink size={12} />
                  Open
                </button>
              </div>
              {selectedChunk.section_label ? (
                <div className="rounded-xl bg-muted/50 p-3 text-xs">
                  <span className="font-semibold">Section: </span>{selectedChunk.section_label}
                </div>
              ) : null}
              <div className="whitespace-pre-wrap break-words rounded-xl bg-muted/30 p-3 text-xs leading-relaxed text-foreground/85">
                {selectedChunk.content}
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground">Select a chunk to inspect evidence.</div>
          )}
        </div>
      </div>
    </div>
  )
}
