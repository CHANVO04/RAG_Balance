import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { DEFAULT_QUERY_MODE, QueryMode } from './searchStore'

export interface Workspace {
  id: string
  name: string
  icon: string
  collectionName: string
  systemPrompt: string
  createdAt: string
  strategy?: QueryMode
  isSetupComplete?: boolean
}

function createDefaultWorkspace(): Workspace {
  return {
    id: 'default',
    name: 'General Science',
    icon: '🔬',
    collectionName: 'scientific_papers',
    systemPrompt: 'You are a helpful scientific research assistant.',
    createdAt: new Date().toISOString(),
    strategy: DEFAULT_QUERY_MODE,
    isSetupComplete: true,
  }
}

interface WorkspaceState {
  workspaces: Workspace[]
  activeWorkspaceId: string
  addWorkspace: (workspace: Workspace) => void
  removeWorkspace: (id: string) => void
  setActiveWorkspace: (id: string) => void
  updateWorkspace: (id: string, updates: Partial<Workspace>) => void
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      workspaces: [
        createDefaultWorkspace(),
      ],
      activeWorkspaceId: 'default',
      addWorkspace: (ws) => set((s) => ({
        workspaces: [...s.workspaces, ws],
        activeWorkspaceId: ws.id,
      })),
      removeWorkspace: (id) => set((s) => {
        if (id === 'default') {
          const hasDefault = s.workspaces.some((w) => w.id === 'default')
          return {
            workspaces: hasDefault
              ? s.workspaces.map((w) => w.id === 'default' ? createDefaultWorkspace() : w)
              : [createDefaultWorkspace(), ...s.workspaces],
            activeWorkspaceId: s.activeWorkspaceId === 'default' ? 'default' : s.activeWorkspaceId,
          }
        }

        const remaining = s.workspaces.filter(w => w.id !== id)
        const fallback = remaining.find((w) => w.isSetupComplete)?.id || remaining[0]?.id || 'default'
        return {
          workspaces: remaining.length ? remaining : [createDefaultWorkspace()],
          activeWorkspaceId: s.activeWorkspaceId === id ? fallback : s.activeWorkspaceId,
        }
      }),
      setActiveWorkspace: (id) => set((s) => ({
        activeWorkspaceId: s.workspaces.some((w) => w.id === id) ? id : s.activeWorkspaceId,
      })),
      updateWorkspace: (id, updates) => set((s) => ({
        workspaces: s.workspaces.map((w) => {
          if (w.id !== id) return w
          if (!w.isSetupComplete) return { ...w, ...updates }
          const { strategy: _ignoredStrategy, ...safeUpdates } = updates
          return { ...w, ...safeUpdates, strategy: w.strategy ?? DEFAULT_QUERY_MODE }
        })
      })),
    }),
    { name: 'workspace-storage' }
  )
)
