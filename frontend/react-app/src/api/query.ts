import { DocumentInfo } from '../store'

export interface GraphNode {
  id: string
  label: string
  type?: string
  mentions: number
  degree: number
  source_files?: string[]
  pages?: number[]
}

export interface GraphEdge {
  id?: string
  source: string
  target: string
  relation: string
  weight: number
  confidence?: number
  source_file?: string
  page?: number
  source_files?: string[]
  pages?: number[]
  chunk_ids?: string[]
  visual_ids?: string[]
  evidence_preview?: string
}

export interface GraphData { nodes: GraphNode[]; edges: GraphEdge[] }
export interface UMAPPoint { x: number; y: number; file_name: string; chunk_id: string; label: string }
export interface QueryDefaultPrompts { system_prompt: string; user_prompt_template: string }
export interface VectorChunk {
  chunk_id: string
  file_name: string
  chunk_index: number
  page: number
  section_label: string
  doc_type: string
  content: string
  has_table: boolean
  has_formula: boolean
  has_image: boolean
}

async function responseError(response: Response, fallback: string) {
  const text = await response.text()
  if (!text) return `${fallback} (HTTP ${response.status})`

  try {
    const payload = JSON.parse(text)
    const detail = payload?.detail ?? payload?.message ?? payload?.error
    if (typeof detail === 'string') return `${detail} (HTTP ${response.status})`
  } catch {
    return `${text} (HTTP ${response.status})`
  }

  return `${fallback} (HTTP ${response.status})`
}

export async function fetchGraph(workspaceId = 'default', includeChunks = false): Promise<GraphData> {
  const params = new URLSearchParams({
    workspace_id: workspaceId,
    include_chunks: includeChunks ? 'true' : 'false',
  })
  const r = await fetch(`/api/graph?${params.toString()}`)
  if (!r.ok) throw new Error(await responseError(r, 'Graph fetch failed'))
  return r.json()
}

export async function fetchUMAP(workspaceId = 'default'): Promise<UMAPPoint[]> {
  const r = await fetch(`/api/umap?workspace_id=${encodeURIComponent(workspaceId)}`)
  if (!r.ok) throw new Error('UMAP fetch failed')
  return r.json()
}

export async function fetchVectorChunks(workspaceId = 'default', limit = 500): Promise<VectorChunk[]> {
  const params = new URLSearchParams({
    workspace_id: workspaceId,
    limit: String(limit),
  })
  const r = await fetch(`/api/chunks?${params.toString()}`)
  if (!r.ok) throw new Error(await responseError(r, 'Chunk fetch failed'))
  return r.json()
}

export async function fetchDocuments(workspaceId = 'default'): Promise<DocumentInfo[]> {
  const r = await fetch(`/api/documents?workspace_id=${encodeURIComponent(workspaceId)}`)
  if (!r.ok) throw new Error('Documents fetch failed')
  return r.json()
}

export async function fetchQueryDefaultPrompts(): Promise<QueryDefaultPrompts> {
  const r = await fetch('/api/query-default-prompts')
  if (!r.ok) throw new Error(await responseError(r, 'Default prompt fetch failed'))
  return r.json()
}

export async function deleteDocument(fileName: string, workspaceId = 'default'): Promise<void> {
  const r = await fetch(`/api/documents/${encodeURIComponent(fileName)}?workspace_id=${encodeURIComponent(workspaceId)}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(await responseError(r, 'Delete failed'))
}
