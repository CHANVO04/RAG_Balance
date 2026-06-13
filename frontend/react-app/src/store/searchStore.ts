import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type QueryMode = 'hybrid' | 'only_vector_fast' | 'only_vector_multimodal'

export const DEFAULT_QUERY_MODE: QueryMode = 'only_vector_multimodal'

export interface WorkspaceSearchSettings {
  topK: number
  qdrantLimit: number
  scoreThreshold: number
  maxContextChunks: number
  temperature: number
  maxInputTokens: number
  maxOutputTokens: number
  customSystemInstruction: string
  userPromptTemplate: string
  mode: QueryMode
  selectedFiles: string[]
  useCache: boolean
}

interface SearchState {
  byWorkspace: Record<string, WorkspaceSearchSettings>
  byConversation: Record<string, WorkspaceSearchSettings>
  getSettings: (workspaceId: string, conversationId?: string | null) => WorkspaceSearchSettings
  setTopK: (workspaceId: string, conversationId: string | null, topK: number) => void
  setQdrantLimit: (workspaceId: string, conversationId: string | null, qdrantLimit: number) => void
  setScoreThreshold: (workspaceId: string, conversationId: string | null, scoreThreshold: number) => void
  setMaxContextChunks: (workspaceId: string, conversationId: string | null, maxContextChunks: number) => void
  setTemperature: (workspaceId: string, conversationId: string | null, temperature: number) => void
  setMaxInputTokens: (workspaceId: string, conversationId: string | null, maxInputTokens: number) => void
  setMaxOutputTokens: (workspaceId: string, conversationId: string | null, maxOutputTokens: number) => void
  setCustomSystemInstruction: (workspaceId: string, conversationId: string | null, customSystemInstruction: string) => void
  setUserPromptTemplate: (workspaceId: string, conversationId: string | null, userPromptTemplate: string) => void
  setMode: (workspaceId: string, conversationId: string | null, mode: QueryMode) => void
  setSelectedFiles: (workspaceId: string, conversationId: string | null, selectedFiles: string[]) => void
  setUseCache: (workspaceId: string, conversationId: string | null, useCache: boolean) => void
  clearWorkspaceSettings: (workspaceId: string) => void
}

export const DEFAULT_USER_PROMPT_TEMPLATE = 'Context:\n{context}\n\nQuestion: {question}'

const defaults: WorkspaceSearchSettings = {
  topK: 30,
  qdrantLimit: 30,
  scoreThreshold: 0.58,
  maxContextChunks: 8,
  temperature: 0.2,
  maxInputTokens: 8000,
  maxOutputTokens: 1024,
  customSystemInstruction: '',
  userPromptTemplate: DEFAULT_USER_PROMPT_TEMPLATE,
  mode: DEFAULT_QUERY_MODE,
  selectedFiles: [],
  useCache: true,
}

function normalizeSettings(settings?: WorkspaceSearchSettings): WorkspaceSearchSettings {
  if (!settings) return defaults
  const legacyMode = settings.mode as string
  const mode: QueryMode =
        legacyMode === 'hybrid'
          ? 'hybrid'
          : legacyMode === 'only_vector_fast'
            ? 'only_vector_fast'
            : DEFAULT_QUERY_MODE
  const qdrantLimit = settings.qdrantLimit ?? defaults.qdrantLimit
  const useCache = settings.useCache ?? defaults.useCache
  return { ...defaults, ...settings, topK: qdrantLimit, qdrantLimit, mode, useCache }
}

export const useSearchStore = create<SearchState>()(
  persist(
    (set, get) => ({
      byWorkspace: {},
      byConversation: {},
      getSettings: (workspaceId, conversationId) => {
        if (conversationId) {
          const conversationSettings = get().byConversation[conversationId]
          if (conversationSettings) return normalizeSettings(conversationSettings)
        }
        return normalizeSettings(get().byWorkspace[workspaceId])
      },
      setTopK: (workspaceId, conversationId, topK) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, topK, qdrantLimit: topK }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      setQdrantLimit: (workspaceId, conversationId, qdrantLimit) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, topK: qdrantLimit, qdrantLimit }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      setScoreThreshold: (workspaceId, conversationId, scoreThreshold) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, scoreThreshold }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      setMaxContextChunks: (workspaceId, conversationId, maxContextChunks) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, maxContextChunks }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      setTemperature: (workspaceId, conversationId, temperature) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, temperature }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      setMaxInputTokens: (workspaceId, conversationId, maxInputTokens) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, maxInputTokens }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      setMaxOutputTokens: (workspaceId, conversationId, maxOutputTokens) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, maxOutputTokens }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      setCustomSystemInstruction: (workspaceId, conversationId, customSystemInstruction) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, customSystemInstruction }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      setUserPromptTemplate: (workspaceId, conversationId, userPromptTemplate) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, userPromptTemplate }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      setMode: (workspaceId, conversationId, mode) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, mode }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      setSelectedFiles: (workspaceId, conversationId, selectedFiles) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, selectedFiles }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      setUseCache: (workspaceId, conversationId, useCache) => set((s) => {
        const current = s.byConversation[conversationId ?? ''] ?? s.byWorkspace[workspaceId] ?? defaults
        const next = { ...current, useCache }
        return {
          byWorkspace: { ...s.byWorkspace, [workspaceId]: next },
          byConversation: conversationId ? { ...s.byConversation, [conversationId]: next } : s.byConversation
        }
      }),
      clearWorkspaceSettings: (workspaceId) => set((s) => {
        const nextWorkspace = { ...s.byWorkspace }
        delete nextWorkspace[workspaceId]
        return { byWorkspace: nextWorkspace }
      }),
    }),
    { name: 'scientific-rag-search-storage' },
  ),
)
