import { useEffect, useRef } from 'react'
import { useStore } from '../store'
import { useQueryClient } from '@tanstack/react-query'
import { useToastStore } from '../store/toastStore'
import { useWorkspaceStore } from '../store/workspaceStore'

export function useIngestPoll() {
  const { activeTaskId, activeTaskWorkspaceId, updateTaskStatus } = useStore()
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const qc = useQueryClient()
  const pushToast = useToastStore((s) => s.pushToast)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const notifiedRef = useRef<string | null>(null)
  const taskWorkspaceId = activeTaskWorkspaceId || activeWorkspaceId

  useEffect(() => {
    if (!activeTaskId) {
      if (intervalRef.current) clearInterval(intervalRef.current)
      return
    }

    const poll = async () => {
      try {
        const r = await fetch(`/api/task-status/${activeTaskId}`)
        if (!r.ok) return
        const status = await r.json()
        updateTaskStatus(status)
        if (status.status === 'done' || status.status === 'error') {
          qc.invalidateQueries({ queryKey: ['documents', taskWorkspaceId] })
          qc.invalidateQueries({ queryKey: ['graph', taskWorkspaceId] })
          qc.invalidateQueries({ queryKey: ['umap', taskWorkspaceId] })
          if (notifiedRef.current !== `${activeTaskId}:${status.status}`) {
            notifiedRef.current = `${activeTaskId}:${status.status}`
            pushToast({
              type: status.status === 'done' ? 'success' : 'error',
              title: status.status === 'done' ? 'Ingest completed' : 'Ingest failed',
              description: status.error || status.current_step,
            })
          }
          if (intervalRef.current) clearInterval(intervalRef.current)
        }
      } catch {
        // network error — keep polling
      }
    }

    poll() // immediate first poll
    intervalRef.current = setInterval(poll, 3000)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [activeTaskId, qc, pushToast, taskWorkspaceId, updateTaskStatus])
}
