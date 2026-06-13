import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { useSearchStore } from './searchStore'

export interface SourceInfo {
  id: number
  citation_id?: string
  ref_id?: string
  kind?: 'text' | 'image' | 'formula' | 'table'
  visual_id?: string
  asset_path?: string
  asset_url?: string
  content?: string
  file_name: string
  page: number
  score: number
  section_label: string
  has_table: boolean
  has_formula: boolean
  has_image: boolean
  pdf_url: string
  display: string
}

export interface KGEvidenceInfo {
  id: string
  subject: string
  relation: string
  object: string
  subject_id?: string
  object_id?: string
  edge_id?: string
  source_file?: string
  page?: number
  chunk_id?: string
  weight?: number
  evidence_preview?: string
  has_document_evidence?: boolean
}

export interface DocumentInfo {
  file_name: string
  chunk_count: number
  ingested_at: string
  sha256: string
  total_pages: number
  file_size?: number | null
  status?: 'ready' | 'processing' | 'error'
  ingest_mode?: string
  processing_time_seconds?: number | null
  stage_timings?: Record<string, number>
  embedding?: {
    model?: string
    input_tokens?: number
    price_per_1m_tokens?: number
    cost_usd?: number
  } | null
  total_tables?: number
  total_formulas?: number
  total_images?: number
}

export interface TaskStatus {
  task_id: string
  status: string
  progress: number
  current_step: string
  logs: string[]
  error?: string
  queued_at?: number | null
  started_at?: number | null
  completed_at?: number | null
  elapsed_ms?: number | null
  stage_timings_ms?: Record<string, Record<string, number>>
}

export interface Conversation {
  id: string
  workspaceId: string
  title: string
  createdAt: string
}

export type SegmentType = 'text' | 'latex_inline' | 'latex_block' | 'cite' | 'kg_cite'
export interface Segment { type: SegmentType; content: string }

export interface GraphFocus {
  nodeIds: string[]
  edgeId?: string
  evidenceId?: string
}

export interface AgentStep {
  id: string
  label: string
  status: 'pending' | 'running' | 'completed' | 'error'
  duration?: number
  startedAt?: number
  completedAt?: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  segments: Segment[]
  sources: SourceInfo[]
  thought?: string
  thinkingComplete?: boolean
  steps?: AgentStep[]
  isStreaming?: boolean
  kgSources?: KGEvidenceInfo[]
  retrievalTrace?: Record<string, unknown>
}

interface AppState {
  conversations: Conversation[]
  activeConversationByWorkspace: Record<string, string>
  activeConversationId: string | null
  messagesByConversation: Record<string, Message[]>
  messages: Message[]
  currentFile: string | null
  currentPage: number
  currentSource: SourceInfo | null
  sources: SourceInfo[]
  activeTaskId: string | null
  activeTaskWorkspaceId: string | null
  taskStatus: TaskStatus | null
  rightTab: 'pdf' | 'kg' | 'analytics' | 'umap' | 'docs'
  graphFocus: GraphFocus | null

  newConversation: (workspaceId: string) => void
  setActiveConversation: (id: string) => void
  addMessage: (msg: Message) => void
  updateMessage: (id: string, updater: (msg: Message) => Message) => void
  updateLastMessage: (updater: (msg: Message) => Message) => void
  setPDF: (file: string, page: number, source?: SourceInfo | null) => void
  activateSource: (source: SourceInfo) => void
  clearActiveSource: () => void
  setSources: (sources: SourceInfo[]) => void
  setTask: (id: string, workspaceId?: string | null) => void
  updateTaskStatus: (status: TaskStatus) => void
  clearTask: () => void
  setRightTab: (tab: AppState['rightTab']) => void
  focusGraphEvidence: (evidence: KGEvidenceInfo) => void
  clearGraphFocus: () => void
  deleteConversation: (id: string) => void
  purgeWorkspaceLocalData: (workspaceId: string) => void
}

function firstTitleFromMessage(text: string) {
  const trimmed = text.trim().replace(/\s+/g, ' ')
  return trimmed.length > 42 ? `${trimmed.slice(0, 42)}...` : trimmed || 'New conversation'
}

export const useStore = create<AppState>()(
  persist(
    (set, get) => ({
      conversations: [],
      activeConversationByWorkspace: {},
      activeConversationId: null,
      messagesByConversation: {},
      messages: [],
      currentFile: null,
      currentPage: 1,
      currentSource: null,
      sources: [],
      activeTaskId: null,
      activeTaskWorkspaceId: null,
      taskStatus: null,
      rightTab: 'docs',
      graphFocus: null,

      newConversation: (workspaceId: string) => {
        const id = crypto.randomUUID()
        
        // Copy workspace settings to conversation settings but turn off cache by default
        const workspaceSettings = useSearchStore.getState().getSettings(workspaceId)
        useSearchStore.setState((s) => ({
          byConversation: {
            ...s.byConversation,
            [id]: {
              ...workspaceSettings,
              useCache: false // Disable cache query for new chats by default to allow comparison
            }
          }
        }))

        set((s) => ({
          conversations: [
            { id, workspaceId, title: 'New conversation', createdAt: new Date().toISOString() },
            ...s.conversations,
          ],
          activeConversationByWorkspace: { ...s.activeConversationByWorkspace, [workspaceId]: id },
          activeConversationId: id,
          messagesByConversation: { ...s.messagesByConversation, [id]: [] },
          messages: [],
          sources: [],
          currentFile: null,
          currentPage: 1,
          currentSource: null,
          graphFocus: null,
        }))
      },

      setActiveConversation: (id) => set((s) => {
        if (s.activeConversationId === id && s.messages === (s.messagesByConversation[id] ?? [])) {
          return s
        }
        const conv = s.conversations.find((c) => c.id === id)
        const nextMessages = s.messagesByConversation[id] ?? []
        const nextSources = nextMessages.flatMap((m) => m.sources ?? [])
        return {
          activeConversationId: id,
          activeConversationByWorkspace: conv
            ? s.activeConversationByWorkspace[conv.workspaceId] === id
              ? s.activeConversationByWorkspace
              : { ...s.activeConversationByWorkspace, [conv.workspaceId]: id }
            : s.activeConversationByWorkspace,
          messages: nextMessages,
          sources: nextSources,
          currentSource: null,
          currentFile: null,
          graphFocus: null,
        }
      }),

      addMessage: (msg) => set((s) => {
        if (!s.activeConversationId) return s
        const current = s.messagesByConversation[s.activeConversationId] ?? []
        const nextMessages = [...current, msg]
        const shouldRename = msg.role === 'user' && current.length === 0
        return {
          messages: nextMessages,
          messagesByConversation: { ...s.messagesByConversation, [s.activeConversationId]: nextMessages },
          conversations: shouldRename
            ? s.conversations.map((c) => c.id === s.activeConversationId ? { ...c, title: firstTitleFromMessage(msg.segments[0]?.content ?? '') } : c)
            : s.conversations,
        }
      }),

      updateMessage: (id, updater) => set((s) => {
        if (!s.activeConversationId) return s
        const current = s.messagesByConversation[s.activeConversationId] ?? []
        const nextMessages = current.map((m) => m.id === id ? updater(m) : m)
        return {
          messages: nextMessages,
          messagesByConversation: { ...s.messagesByConversation, [s.activeConversationId]: nextMessages },
        }
      }),

      updateLastMessage: (updater) => {
        const messages = get().messages
        const last = messages.length ? messages[messages.length - 1] : undefined
        if (last) get().updateMessage(last.id, updater)
      },

      setPDF: (file, page, source = null) =>
        set({ currentFile: file, currentPage: page, currentSource: source, rightTab: 'docs' }),

      activateSource: (source) =>
        set({
          currentFile: source.file_name,
          currentPage: source.page,
          currentSource: source,
          rightTab: 'pdf',
        }),

      clearActiveSource: () =>
        set({
          currentFile: null,
          currentPage: 1,
          currentSource: null,
        }),

      setSources: (sources) => set({ sources }),

      setTask: (id, workspaceId = null) => set({
        activeTaskId: id,
        activeTaskWorkspaceId: workspaceId,
        taskStatus: null,
      }),

      updateTaskStatus: (status) => set({ taskStatus: status }),

      clearTask: () => set({
        activeTaskId: null,
        activeTaskWorkspaceId: null,
        taskStatus: null,
      }),

      setRightTab: (tab) => set({ rightTab: tab }),

      focusGraphEvidence: (evidence) => {
        const subjectNode = evidence.subject_id || evidence.subject
        const objectNode = evidence.object_id || evidence.object
        const nodeIds = [subjectNode, objectNode].filter((id): id is string => Boolean(id))

        set({
          rightTab: 'kg',
          graphFocus: {
            nodeIds,
            edgeId: evidence.edge_id,
            evidenceId: evidence.id,
          },
        })
      },

      clearGraphFocus: () => set({ graphFocus: null }),

      deleteConversation: (id) => set((s) => {
        const convToDelete = s.conversations.find((c) => c.id === id)
        if (!convToDelete) return s

        const workspaceId = convToDelete.workspaceId
        const nextConversations = s.conversations.filter((c) => c.id !== id)
        const nextMessagesByConversation = { ...s.messagesByConversation }
        delete nextMessagesByConversation[id]

        let nextActiveId = s.activeConversationId
        let nextMessages = s.messages
        const nextActiveByWorkspace = { ...s.activeConversationByWorkspace }

        if (s.activeConversationId === id) {
          const remaining = nextConversations.filter((c) => c.workspaceId === workspaceId)
          if (remaining.length > 0) {
            nextActiveId = remaining[0].id
            nextMessages = nextMessagesByConversation[nextActiveId] ?? []
            nextActiveByWorkspace[workspaceId] = nextActiveId
          } else {
            // Create a new one
            const newId = crypto.randomUUID()
            nextConversations.unshift({
              id: newId,
              workspaceId,
              title: 'New conversation',
              createdAt: new Date().toISOString()
            })
            nextActiveId = newId
            nextMessages = []
            nextMessagesByConversation[newId] = []
            nextActiveByWorkspace[workspaceId] = newId
          }
        } else if (nextActiveByWorkspace[workspaceId] === id) {
          const remaining = nextConversations.filter((c) => c.workspaceId === workspaceId)
          if (remaining.length > 0) {
            nextActiveByWorkspace[workspaceId] = remaining[0].id
          } else {
            const newId = crypto.randomUUID()
            nextConversations.unshift({
              id: newId,
              workspaceId,
              title: 'New conversation',
              createdAt: new Date().toISOString()
            })
            nextMessagesByConversation[newId] = []
            nextActiveByWorkspace[workspaceId] = newId
          }
        }

        return {
          conversations: nextConversations,
          messagesByConversation: nextMessagesByConversation,
          activeConversationId: nextActiveId,
          messages: nextMessages,
          activeConversationByWorkspace: nextActiveByWorkspace,
          graphFocus: null,
        }
      }),

      purgeWorkspaceLocalData: (workspaceId) => set((s) => {
        const removedIds = new Set(
          s.conversations.filter((conv) => conv.workspaceId === workspaceId).map((conv) => conv.id),
        )
        if (removedIds.size === 0) {
          const nextActiveByWorkspace = { ...s.activeConversationByWorkspace }
          delete nextActiveByWorkspace[workspaceId]
          return {
            activeConversationByWorkspace: nextActiveByWorkspace,
            currentFile: null,
            currentPage: 1,
            currentSource: null,
            sources: [],
            graphFocus: null,
          }
        }

        const nextMessagesByConversation = { ...s.messagesByConversation }
        removedIds.forEach((id) => {
          delete nextMessagesByConversation[id]
        })

        const nextActiveByWorkspace = { ...s.activeConversationByWorkspace }
        delete nextActiveByWorkspace[workspaceId]
        const activeRemoved = s.activeConversationId ? removedIds.has(s.activeConversationId) : false

        return {
          conversations: s.conversations.filter((conv) => conv.workspaceId !== workspaceId),
          activeConversationByWorkspace: nextActiveByWorkspace,
          activeConversationId: activeRemoved ? null : s.activeConversationId,
          messagesByConversation: nextMessagesByConversation,
          messages: activeRemoved ? [] : s.messages,
          currentFile: null,
          currentPage: 1,
          currentSource: null,
          sources: activeRemoved ? [] : s.sources,
          graphFocus: null,
        }
      }),
    }),
    {
      name: 'scientific-rag-chat-storage',
      partialize: (s) => ({
        conversations: s.conversations,
        activeConversationByWorkspace: s.activeConversationByWorkspace,
        activeConversationId: s.activeConversationId,
        messagesByConversation: s.messagesByConversation,
      }),
      onRehydrateStorage: () => (state) => {
        if (state?.activeConversationId) {
          state.messages = state.messagesByConversation[state.activeConversationId] ?? []
          state.sources = state.messages.flatMap((m) => m.sources ?? [])
        }
      },
    },
  ),
)
