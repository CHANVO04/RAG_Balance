import React, { useCallback, useEffect, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { AlertCircle, Upload, X, FileText, CheckCircle2, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import { DocumentInfo, useStore } from '../../store'
import DocumentChip from './DocumentChip'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { deleteDocument, fetchDocuments } from '../../api/query'
import { Skeleton } from '../ui/Skeleton'
import { useToastStore } from '../../store/toastStore'
import { motion } from 'framer-motion'
import { DEFAULT_QUERY_MODE } from '../../store/searchStore'
import ConfirmDialog from '../ui/ConfirmDialog'
import { formatDuration, getIngestTimingSummary, type IngestTimingSnapshot } from '../../lib/ingestTiming'

type QueuedFileStatus = 'pending' | 'uploading' | 'ingesting' | 'done' | 'error'

interface QueuedFile {
  id: string
  file: File
  status: QueuedFileStatus
  error?: string
  timing?: IngestTimingSnapshot
}

function fileQueueKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function stageTimingEntries(stageTimings?: Record<string, Record<string, number>>) {
  return Object.entries(stageTimings ?? {}).flatMap(([fileName, timings]) => (
    Object.entries(timings).map(([stage, ms]) => ({ fileName, stage, ms }))
  ))
}

function formatStageName(stage: string) {
  return stage
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export default function DocumentManagement() {
  const { setTask, taskStatus, activeTaskWorkspaceId, updateTaskStatus, currentFile, clearActiveSource } = useStore()
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const activeWorkspaceStrategy = useWorkspaceStore((s) => (
    s.workspaces.find((workspace) => workspace.id === s.activeWorkspaceId)?.strategy ?? DEFAULT_QUERY_MODE
  ))
  const qc = useQueryClient()
  const [queuedFiles, setQueuedFiles] = useState<QueuedFile[]>([])
  const [pendingDeleteDoc, setPendingDeleteDoc] = useState<DocumentInfo | null>(null)
  const [uploading, setUploading] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const pushToast = useToastStore((s) => s.pushToast)

  const { data: documents = [], isLoading } = useQuery({
    queryKey: ['documents', activeWorkspaceId],
    queryFn: () => fetchDocuments(activeWorkspaceId)
  })

  useEffect(() => {
    setQueuedFiles([])
    setUploading(false)
  }, [activeWorkspaceId])

  useEffect(() => {
    const hasRunningTiming = queuedFiles.some((item) => item.timing?.startedAt && !item.timing.readyAt && !item.timing.endedAt)
    if (!hasRunningTiming) return

    const timer = window.setInterval(() => setNow(Date.now()), 100)
    return () => window.clearInterval(timer)
  }, [queuedFiles])

  const deleteMutation = useMutation({
    mutationFn: (fileName: string) => deleteDocument(fileName, activeWorkspaceId),
    onSuccess: (_, fileName) => {
      pushToast({ type: 'success', title: 'Document deleted', description: fileName })
      if (currentFile === fileName) clearActiveSource()
      qc.invalidateQueries({ queryKey: ['documents', activeWorkspaceId] })
      qc.invalidateQueries({ queryKey: ['graph', activeWorkspaceId] })
      qc.invalidateQueries({ queryKey: ['umap', activeWorkspaceId] })
      setPendingDeleteDoc(null)
    },
    onError: (error) => {
      pushToast({ type: 'error', title: 'Delete failed', description: (error as Error).message })
    },
  })

  const onDrop = useCallback((files: File[]) => {
    setQueuedFiles((current) => {
      const existing = new Set(current.map((item) => fileQueueKey(item.file)))
      const next = files
        .filter((file) => !existing.has(fileQueueKey(file)))
        .map((file) => ({
          id: crypto.randomUUID(),
          file,
          status: 'pending' as const,
        }))
      return [...current, ...next]
    })
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
      'text/html': ['.html', '.htm'],
    },
    maxSize: 50 * 1024 * 1024,
    multiple: true,
  })

  const setQueuedFileStatus = (id: string, status: QueuedFileStatus, error?: string) => {
    setQueuedFiles((items) => items.map((item) => (
      item.id === id ? { ...item, status, error } : item
    )))
  }

  const updateQueuedFileTiming = (id: string, timing: Partial<IngestTimingSnapshot>) => {
    setQueuedFiles((items) => items.map((item) => (
      item.id === id ? { ...item, timing: { ...item.timing, ...timing } } : item
    )))
  }

  const removeQueuedFile = (id: string) => {
    if (uploading) return
    setQueuedFiles((items) => items.filter((item) => item.id !== id))
  }

  const pollTaskUntilFinished = async (taskId: string) => {
    while (true) {
      await sleep(1500)
      const r = await fetch(`/api/task-status/${taskId}`)
      if (!r.ok) throw new Error(await r.text())
      const status = await r.json()
      updateTaskStatus(status)
      if (status.status === 'done' || status.status === 'error') {
        return status
      }
    }
  }

  const runIngestItems = async (items: QueuedFile[]) => {
    if (!items.length) return
    setUploading(true)
    const mode = activeWorkspaceStrategy
    try {
      for (const item of items) {
        try {
          const startedAt = Date.now()
          setNow(startedAt)
          setQueuedFiles((current) => current.map((queued) => (
            queued.id === item.id
              ? { ...queued, status: 'uploading', error: undefined, timing: { startedAt } }
              : queued
          )))
          const fd = new FormData()
          fd.append('file', item.file)
          const r = await fetch(
            `/api/ingest?workspace_id=${encodeURIComponent(activeWorkspaceId)}&ingest_mode=${encodeURIComponent(mode)}`,
            { method: 'POST', body: fd },
          )
          if (!r.ok) throw new Error(await r.text())
          const data = await r.json()
          const uploadedAt = Date.now()
          setNow(uploadedAt)
          updateQueuedFileTiming(item.id, {
            uploadedAt,
            estimatedMinutes: data.estimated_minutes,
          })
          setTask(data.task_id, activeWorkspaceId)
          updateTaskStatus({
            task_id: data.task_id,
            status: data.status,
            progress: 0,
            current_step: `Chờ xử lý: ${data.file_name ?? item.file.name}`,
            logs: [`File '${data.file_name ?? item.file.name}' đã được upload.`],
          })
          setQueuedFileStatus(item.id, 'ingesting')
          pushToast({ type: 'success', title: 'Upload queued', description: `${data.file_name ?? item.file.name} is being ingested.` })
          const finalStatus = await pollTaskUntilFinished(data.task_id)
          if (finalStatus.status === 'error') {
            const endedAt = Date.now()
            setNow(endedAt)
            updateQueuedFileTiming(item.id, {
              endedAt,
              outcome: 'error',
              backendElapsedMs: finalStatus.elapsed_ms ?? undefined,
              stageTimingsMs: finalStatus.stage_timings_ms,
            })
            throw new Error(finalStatus.error || `${item.file.name} ingest failed.`)
          }
          await Promise.all([
            qc.invalidateQueries({ queryKey: ['documents', activeWorkspaceId] }),
            qc.invalidateQueries({ queryKey: ['graph', activeWorkspaceId] }),
            qc.invalidateQueries({ queryKey: ['umap', activeWorkspaceId] }),
          ])
          const readyAt = Date.now()
          setNow(readyAt)
          updateQueuedFileTiming(item.id, {
            readyAt,
            outcome: 'ready',
            backendElapsedMs: finalStatus.elapsed_ms ?? undefined,
            stageTimingsMs: finalStatus.stage_timings_ms,
          })
          setQueuedFileStatus(item.id, 'done')
        } catch (e) {
          const message = (e as Error).message
          const endedAt = Date.now()
          setNow(endedAt)
          console.error(e)
          updateQueuedFileTiming(item.id, { endedAt, outcome: 'error' })
          setQueuedFileStatus(item.id, 'error', message)
          pushToast({ type: 'error', title: 'Upload failed', description: message })
        }
      }
      if (items.length > 1) {
        pushToast({ type: 'success', title: 'Queue finished', description: 'Sequential ingest queue has completed.' })
      }
    } finally {
      setUploading(false)
    }
  }

  const handleUpload = async () => {
    const pendingItems = queuedFiles.filter((item) => item.status === 'pending' || item.status === 'error')
    await runIngestItems(pendingItems)
  }

  const handleUploadOne = async (item: QueuedFile) => {
    if (item.status !== 'pending' && item.status !== 'error') return
    await runIngestItems([item])
  }

  const visibleTaskStatus = activeTaskWorkspaceId === activeWorkspaceId ? taskStatus : null
  const isActive = visibleTaskStatus?.status === 'processing' || visibleTaskStatus?.status === 'queued'
  const isDone = visibleTaskStatus?.status === 'done'
  const isError = visibleTaskStatus?.status === 'error'
  const activeStageTimings = stageTimingEntries(visibleTaskStatus?.stage_timings_ms)

  return (
    <div className="flex flex-col h-full min-h-0 bg-background overflow-y-auto">
      {/* Upload Zone */}
      <div className="shrink-0 p-6 border-b border-border/50">
        <div
          {...getRootProps()}
          className={cn(
            "group relative border-2 border-dashed rounded-3xl p-8 text-center transition-all cursor-pointer",
            isDragActive ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-accent/30"
          )}
        >
          <input {...getInputProps()} />
          <motion.div
            whileHover={{ scale: 1.06 }}
            className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center text-primary mx-auto mb-4 transition-transform"
          >
            <Upload size={24} />
          </motion.div>
          <h3 className="text-sm font-bold mb-1">Upload Scientific Papers</h3>
          <p className="text-xs text-muted-foreground">PDF, DOCX, PPTX, HTML up to 50MB</p>
          
          {isDragActive && (
            <div className="absolute inset-0 bg-primary/10 backdrop-blur-[2px] rounded-3xl flex items-center justify-center">
              <span className="text-primary font-bold animate-bounce">Drop files here</span>
            </div>
          )}
        </div>

        {queuedFiles.length > 0 && (
          <div className="mt-4 rounded-2xl bg-card border border-border p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-bold">{queuedFiles.length} file{queuedFiles.length > 1 ? 's' : ''} selected</p>
                <p className="text-[10px] text-muted-foreground">Run one file or ingest all sequentially.</p>
              </div>
              <motion.button
                whileHover={{ y: -1 }}
                whileTap={{ scale: 0.96 }}
                onClick={handleUpload}
                disabled={uploading || queuedFiles.every((item) => item.status === 'done')}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-xl text-xs font-bold shadow-lg shadow-primary/20 flex items-center gap-2"
              >
                {uploading ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                Ingest all
              </motion.button>
            </div>
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {queuedFiles.map((item) => (
                <div key={item.id} className="flex items-center justify-between gap-3 rounded-xl bg-accent/35 px-3 py-2">
                  <div className="flex items-center gap-3 min-w-0">
                    {item.status === 'ingesting' || item.status === 'uploading'
                      ? <Loader2 size={15} className="animate-spin text-primary shrink-0" />
                      : item.status === 'done'
                        ? <CheckCircle2 size={15} className="text-green-600 shrink-0" />
                        : item.status === 'error'
                          ? <AlertCircle size={15} className="text-destructive shrink-0" />
                          : <FileText size={15} className="text-primary shrink-0" />}
                    <div className="min-w-0">
                      <p className="text-xs font-bold truncate">{item.file.name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {(item.file.size / 1024 / 1024).toFixed(2)} MB · {item.status}
                      </p>
                      {item.timing?.startedAt && (
                        <p className="text-[10px] text-primary/80 font-semibold">
                          {getIngestTimingSummary(item.timing, now)}
                        </p>
                      )}
                      {item.error && <p className="text-[10px] text-destructive truncate">{item.error}</p>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {(item.status === 'pending' || item.status === 'error') && (
                      <motion.button
                        whileTap={{ scale: 0.96 }}
                        onClick={() => handleUploadOne(item)}
                        disabled={uploading}
                        className="px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground text-[10px] font-bold disabled:opacity-40"
                      >
                        Ingest
                      </motion.button>
                    )}
                    <motion.button
                      whileTap={{ scale: 0.96 }}
                      onClick={() => removeQueuedFile(item.id)}
                      disabled={uploading}
                      className="p-2 rounded-xl hover:bg-background disabled:opacity-40"
                    >
                      <X size={14} />
                    </motion.button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {visibleTaskStatus && (
          <div className="mt-4 rounded-2xl border border-border bg-card p-4 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                {isActive && <Loader2 size={16} className="animate-spin text-primary shrink-0" />}
                {isDone && <CheckCircle2 size={16} className="text-green-600 shrink-0" />}
                {isError && <AlertCircle size={16} className="text-destructive shrink-0" />}
                <div className="min-w-0">
                  <p className="text-xs font-bold truncate">{visibleTaskStatus.current_step}</p>
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
                    {visibleTaskStatus.status} · {visibleTaskStatus.progress}%
                  </p>
                  <p className="text-[10px] text-primary/80 font-semibold">
                    {visibleTaskStatus.elapsed_ms !== undefined && visibleTaskStatus.elapsed_ms !== null
                      ? `Backend ingest ${formatDuration(visibleTaskStatus.elapsed_ms)}`
                      : isActive && visibleTaskStatus.started_at
                        ? `Running ${formatDuration(now - visibleTaskStatus.started_at * 1000)}`
                        : 'Waiting for backend timing'}
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-3 h-1.5 rounded-full bg-accent overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full transition-all',
                  isError ? 'bg-destructive' : isDone ? 'bg-green-600' : 'bg-primary'
                )}
                style={{ width: `${Math.max(4, visibleTaskStatus.progress)}%` }}
              />
            </div>

            {activeStageTimings.length > 0 && (
              <div className="mt-3 rounded-xl bg-muted/60 p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Measured stage timings</p>
                  <p className="text-[10px] font-bold text-primary">
                    Total {formatDuration(visibleTaskStatus.elapsed_ms ?? activeStageTimings.reduce((sum, item) => sum + item.ms, 0))}
                  </p>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  {activeStageTimings.map((item) => (
                    <div key={`${item.fileName}-${item.stage}`} className="rounded-lg bg-background/70 px-2 py-1.5">
                      <p className="truncate text-[10px] font-semibold text-foreground">{formatStageName(item.stage)}</p>
                      <p className="text-[10px] text-muted-foreground">{formatDuration(item.ms)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-3 max-h-44 overflow-y-auto rounded-xl bg-muted/60 p-3 font-mono text-[10px] text-muted-foreground">
              {visibleTaskStatus.logs.slice(-10).map((log, i) => (
                <div key={`${log}-${i}`} className="break-words">{log}</div>
              ))}
              {visibleTaskStatus.error && <div className="text-destructive">{visibleTaskStatus.error}</div>}
            </div>
          </div>
        )}
      </div>

      {/* Document List */}
      <div className="flex-1 min-h-[240px] overflow-y-auto p-6 space-y-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Knowledge Base</h3>
          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-accent text-muted-foreground">{documents.length} Docs</span>
        </div>
        
        {isLoading && [0, 1, 2].map((i) => <Skeleton key={i} variant="shimmer" className="h-32 rounded-2xl" />)}

        {!isLoading && documents.map((doc) => (
          <DocumentChip
            key={doc.sha256 || doc.file_name}
            doc={doc}
            isProcessing={visibleTaskStatus?.status === 'processing' && visibleTaskStatus.current_step.includes(doc.file_name)}
            onDelete={() => setPendingDeleteDoc(doc)}
          />
        ))}

        {!isLoading && documents.length === 0 && (
          <div className="py-20 text-center space-y-4 opacity-50">
            <div className="w-16 h-16 rounded-full border-2 border-dashed border-border flex items-center justify-center mx-auto text-muted-foreground">
              <FileText size={24} />
            </div>
            <p className="text-xs text-muted-foreground">No documents uploaded yet.</p>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={Boolean(pendingDeleteDoc)}
        title="Delete document?"
        description={`This will remove "${pendingDeleteDoc?.file_name ?? ''}" from local files, Qdrant vectors, visual assets, semantic cache, and graph evidence for this workspace.`}
        confirmLabel="Delete document"
        typedValue={pendingDeleteDoc?.file_name}
        isBusy={deleteMutation.isPending}
        onCancel={() => {
          if (!deleteMutation.isPending) setPendingDeleteDoc(null)
        }}
        onConfirm={() => {
          if (pendingDeleteDoc) deleteMutation.mutate(pendingDeleteDoc.file_name)
        }}
      />
    </div>
  )
}
