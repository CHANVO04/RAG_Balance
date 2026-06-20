import React, { useState } from 'react'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { ChevronDown, Plus, Trash2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import { motion, AnimatePresence } from 'framer-motion'
import { useQueryClient } from '@tanstack/react-query'
import { createWorkspaceRemote, deleteWorkspaceRemote } from '../../api/workspaces'
import { useStore } from '../../store'
import { useSearchStore } from '../../store/searchStore'
import { useToastStore } from '../../store/toastStore'
import ConfirmDialog from '../ui/ConfirmDialog'

export default function WorkspaceSwitcher({ collapsed }: { collapsed: boolean }) {
  const { workspaces, activeWorkspaceId, setActiveWorkspace, addWorkspace, removeWorkspace } = useWorkspaceStore()
  const purgeWorkspaceLocalData = useStore((s) => s.purgeWorkspaceLocalData)
  const clearWorkspaceSettings = useSearchStore((s) => s.clearWorkspaceSettings)
  const pushToast = useToastStore((s) => s.pushToast)
  const queryClient = useQueryClient()
  const [isOpen, setIsOpen] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<{ id: string; name: string } | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isCreating, setIsCreating] = useState(false)
  const activeWorkspace = workspaces.find(w => w.id === activeWorkspaceId) || workspaces[0] || {
    id: 'default',
    name: 'General Science',
    icon: 'SR',
    collectionName: 'scientific_papers',
    systemPrompt: 'You are a helpful scientific research assistant.',
    createdAt: new Date().toISOString(),
  }
  const createWorkspace = async () => {
    if (isCreating) return
    const index = workspaces.length + 1
    const workspace = {
      id: `workspace-${Date.now()}`,
      name: `Research Space ${index}`,
      icon: 'SR',
      collectionName: `workspace_${index}`,
      systemPrompt: 'You are a helpful scientific research assistant.',
      createdAt: new Date().toISOString(),
      isSetupComplete: false,
    }
    setIsCreating(true)
    try {
      await createWorkspaceRemote(workspace)
      addWorkspace(workspace)
      setIsOpen(false)
    } catch (err) {
      console.error('Failed to create workspace:', err)
      pushToast({ type: 'error', title: 'Workspace create failed', description: (err as Error).message })
    } finally {
      setIsCreating(false)
    }
  }

  const handleDeleteWorkspace = (e: React.MouseEvent, id: string, name: string) => {
    e.stopPropagation()
    setPendingDelete({ id, name })
  }

  const confirmDeleteWorkspace = async () => {
    if (!pendingDelete) return
    setIsDeleting(true)
    try {
      const report = await deleteWorkspaceRemote(pendingDelete.id)
      purgeWorkspaceLocalData(pendingDelete.id)
      clearWorkspaceSettings(pendingDelete.id)
      removeWorkspace(pendingDelete.id)
      queryClient.removeQueries({ queryKey: ['documents', pendingDelete.id] })
      queryClient.removeQueries({ queryKey: ['graph', pendingDelete.id] })
      queryClient.removeQueries({ queryKey: ['umap', pendingDelete.id] })
      setPendingDelete(null)
      setIsOpen(false)
      pushToast({
        type: 'success',
        title: pendingDelete.id === 'default' ? 'Workspace reset' : 'Workspace deleted',
        description: report?.message || pendingDelete.name,
      })
    } catch (err) {
      console.error('Failed to delete workspace:', err)
      pushToast({ type: 'error', title: 'Workspace delete failed', description: (err as Error).message })
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="relative px-2 py-4 border-b border-border/30">
      {!collapsed && (
        <div className="text-[9px] font-black text-primary tracking-widest px-2 mb-1.5 uppercase select-none">
          Active Workspace
        </div>
      )}
      <button
        onClick={() => !collapsed && setIsOpen(!isOpen)}
        className={cn(
          "flex items-center gap-3 w-full p-2 rounded-xl transition-all duration-200",
          "hover:bg-accent/50 active:scale-[0.98]",
          collapsed ? "justify-center" : "justify-between glass border border-primary/20 shadow-sm hover:border-primary/40 hover:scale-[1.01]"
        )}
      >
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary shrink-0 font-bold border border-primary/20">
            {activeWorkspace.icon}
          </div>
          {!collapsed && (
            <div className="flex flex-col items-start min-w-0 text-left">
              <span className="text-[9px] font-bold text-muted-foreground/60 uppercase tracking-wider leading-none mb-0.5 select-none">Current</span>
              <span className="font-bold text-xs truncate leading-normal text-foreground">{activeWorkspace.name}</span>
            </div>
          )}
        </div>
        {!collapsed && <ChevronDown className={cn("w-4 h-4 text-muted-foreground transition-transform", isOpen && "rotate-180")} />}
      </button>

      <AnimatePresence>
        {isOpen && !collapsed && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="absolute top-full left-2 right-2 mt-2 bg-card border border-border shadow-2xl rounded-xl p-2 z-50 overflow-hidden"
          >
            <div className="text-[10px] font-bold text-muted-foreground px-2 py-1 uppercase tracking-wider">
              Workspaces
            </div>
            {workspaces.map((ws) => (
              <div
                key={ws.id}
                className="group relative flex items-center justify-between w-full rounded-lg hover:bg-accent/50"
              >
                <button
                  onClick={() => {
                    setActiveWorkspace(ws.id)
                    setIsOpen(false)
                  }}
                  className={cn(
                    "flex items-center gap-3 flex-1 p-2 rounded-l-lg text-sm text-left transition-colors",
                    ws.id === activeWorkspaceId ? "bg-primary/10 text-primary" : "hover:bg-accent"
                  )}
                >
                  <span className="w-6 h-6 flex items-center justify-center">{ws.icon}</span>
                  <span className="truncate max-w-[120px]">{ws.name}</span>
                </button>
                <button
                  type="button"
                  onClick={(e) => handleDeleteWorkspace(e, ws.id, ws.name)}
                  className="p-2 text-rose-500 hover:text-rose-700 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                  title="Delete Workspace"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            <div className="h-px bg-border my-2" />
            <button
              onClick={createWorkspace}
              disabled={isCreating}
              className="flex items-center gap-3 w-full p-2 rounded-lg text-sm hover:bg-accent text-muted-foreground italic"
            >
              <Plus className="w-4 h-4" />
              <span>{isCreating ? 'Creating...' : 'Create Workspace'}</span>
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={pendingDelete?.id === 'default' ? 'Reset default workspace?' : 'Delete workspace?'}
        description={`This will permanently remove "${pendingDelete?.name ?? ''}" from local files, Qdrant vectors, visual assets, semantic cache, graph data, and browser chat/search state. This cannot be undone.`}
        confirmLabel={pendingDelete?.id === 'default' ? 'Reset workspace' : 'Delete workspace'}
        typedValue={pendingDelete?.name}
        isBusy={isDeleting}
        onCancel={() => {
          if (!isDeleting) setPendingDelete(null)
        }}
        onConfirm={confirmDeleteWorkspace}
      />
    </div>
  )
}
