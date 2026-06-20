import React, { useCallback, useEffect, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { AlertCircle, Upload, X, FileText, CheckCircle2, Loader2, Trash2 } from 'lucide-react'
import { cn, formatBytes } from '../../lib/utils'
import { DocumentInfo, useStore } from '../../store'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { deleteDocument, fetchDocuments } from '../../api/query'
import { useToastStore } from '../../store/toastStore'
import { motion, AnimatePresence } from 'framer-motion'
import { DEFAULT_QUERY_MODE } from '../../store/searchStore'
import ConfirmDialog from '../ui/ConfirmDialog'
import { getIngestTimingSummary, type IngestTimingSnapshot } from '../../lib/ingestTiming'

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

export default function SidebarDocumentManager({ collapsed }: { collapsed?: boolean }) {
  const { setTask, taskStatus, activeTaskWorkspaceId, updateTaskStatus, currentFile, setPDF, clearActiveSource } = useStore()
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

  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-4 py-2 select-none">
        <div 
          {...getRootProps()} 
          className="w-10 h-10 rounded-xl bg-accent/40 border border-border/50 text-muted-foreground flex items-center justify-center hover:bg-accent hover:text-foreground cursor-pointer transition-colors" 
          title="Upload Scientific Paper"
        >
          <input {...getInputProps()} />
          <Upload size={16} />
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 min-h-0">
      {/* Drag & Drop Area */}
      <div
        {...getRootProps()}
        className={cn(
          "group relative border border-dashed rounded-xl p-4 text-center transition-all cursor-pointer",
          isDragActive ? "border-primary bg-primary/5" : "border-border/60 hover:border-primary/50 hover:bg-accent/40"
        )}
      >
        <input {...getInputProps()} />
        <Upload size={18} className="text-primary mx-auto mb-1.5 transition-transform group-hover:scale-110" />
        <h4 className="text-xs font-bold text-foreground">Upload Scientific Papers</h4>
        <p className="text-[10px] text-muted-foreground mt-0.5">PDF, DOCX, PPTX, HTML up to 50MB</p>
        
        {isDragActive && (
          <div className="absolute inset-0 bg-primary/10 backdrop-blur-[1px] rounded-xl flex items-center justify-center">
            <span className="text-[10px] text-primary font-bold animate-pulse">Drop here</span>
          </div>
        )}
      </div>

      {/* Upload Queue */}
      {queuedFiles.length > 0 && (
        <div className="rounded-xl border border-border/50 bg-card/50 p-2.5 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-bold">{queuedFiles.length} select</span>
            <button
              onClick={handleUpload}
              disabled={uploading || queuedFiles.every((item) => item.status === 'done')}
              className="px-2 py-1 bg-primary text-primary-foreground rounded-lg text-[9px] font-bold shadow-md hover:bg-primary/95 disabled:opacity-40 shrink-0"
            >
              Ingest all
            </button>
          </div>
          <div className="space-y-1.5 max-h-40 overflow-y-auto pr-0.5 scrollbar-thin">
            {queuedFiles.map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-2 rounded-lg bg-accent/20 px-2 py-1">
                <div className="flex items-center gap-1.5 min-w-0">
                  {item.status === 'ingesting' || item.status === 'uploading' ? (
                    <Loader2 size={12} className="animate-spin text-primary shrink-0" />
                  ) : item.status === 'done' ? (
                    <CheckCircle2 size={12} className="text-green-600 shrink-0" />
                  ) : item.status === 'error' ? (
                    <AlertCircle size={12} className="text-destructive shrink-0" />
                  ) : (
                    <FileText size={12} className="text-primary shrink-0" />
                  )}
                  <div className="min-w-0">
                    <p className="text-[10px] font-bold truncate">{item.file.name}</p>
                    <p className="text-[8px] text-muted-foreground">
                      {(item.file.size / 1024 / 1024).toFixed(1)}MB · {item.status}
                    </p>
                    {item.timing?.startedAt && (
                      <p className="text-[8px] text-primary/80 font-semibold truncate">
                        {getIngestTimingSummary(item.timing, now)}
                      </p>
                    )}
                    {item.error && <p className="text-[8px] text-destructive truncate">{item.error}</p>}
                  </div>
                </div>
                <div className="flex items-center gap-0.5 shrink-0">
                  {(item.status === 'pending' || item.status === 'error') && (
                    <button
                      onClick={() => handleUploadOne(item)}
                      disabled={uploading}
                      className="px-1.5 py-0.5 rounded bg-primary text-primary-foreground text-[8px] font-bold disabled:opacity-40"
                    >
                      Ingest
                    </button>
                  )}
                  <button
                    onClick={() => removeQueuedFile(item.id)}
                    disabled={uploading}
                    className="p-1 rounded hover:bg-accent/40 text-muted-foreground"
                  >
                    <X size={10} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Task Status */}
      {visibleTaskStatus && (
        <div className="rounded-xl border border-border/40 bg-card/40 p-2.5 space-y-1.5">
          <div className="flex items-center justify-between gap-2 min-w-0">
            <div className="flex items-center gap-1.5 min-w-0">
              {isActive && <Loader2 size={12} className="animate-spin text-primary shrink-0" />}
              {isDone && <CheckCircle2 size={12} className="text-green-600 shrink-0" />}
              {isError && <AlertCircle size={12} className="text-destructive shrink-0" />}
              <span className="text-[10px] font-bold truncate flex-1">{visibleTaskStatus.current_step}</span>
            </div>
            <span className="text-[8px] font-extrabold uppercase shrink-0 text-muted-foreground">{visibleTaskStatus.progress}%</span>
          </div>

          <div className="h-1 rounded-full bg-accent/40 overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all',
                isError ? 'bg-destructive' : isDone ? 'bg-green-600' : 'bg-primary'
              )}
              style={{ width: `${Math.max(4, visibleTaskStatus.progress)}%` }}
            />
          </div>
        </div>
      )}

      {/* Knowledge Base Document List */}
      <div className="space-y-1.5 flex-1 min-h-0 flex flex-col">
        <div className="flex items-center justify-between py-1 shrink-0 select-none">
          <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Documents</span>
          <span className="text-[9px] font-extrabold px-1.5 py-0.5 rounded bg-accent/70 text-muted-foreground">{documents.length} File{documents.length !== 1 ? 's' : ''}</span>
        </div>
        
        <div className="space-y-1.5 overflow-y-auto flex-1 pr-0.5 scrollbar-thin max-h-72">
          {isLoading && (
            <div className="flex items-center justify-center py-6">
              <Loader2 size={16} className="animate-spin text-muted-foreground" />
            </div>
          )}
          
          {!isLoading && documents.map((doc) => {
            const isSelected = currentFile === doc.file_name
            const isProcessing = visibleTaskStatus?.status === 'processing' && visibleTaskStatus.current_step.includes(doc.file_name)
            return (
              <motion.div
                key={doc.sha256 || doc.file_name}
                layout
                onClick={() => setPDF(doc.file_name, 1)}
                className={cn(
                  "group flex items-center justify-between gap-2 p-2 rounded-xl border border-transparent transition-all cursor-pointer",
                  isSelected 
                    ? "bg-primary/10 border-primary/20 text-primary" 
                    : "hover:bg-accent/40 text-muted-foreground hover:text-foreground",
                  isProcessing && "animate-shimmer overflow-hidden"
                )}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText size={14} className={cn("shrink-0", isSelected ? "text-primary" : "text-muted-foreground/80")} />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold truncate leading-tight">{doc.file_name}</p>
                    <p className="text-[8px] text-muted-foreground/80 font-medium">
                      {doc.file_size ? formatBytes(doc.file_size) : '--'} · {doc.total_pages}p
                    </p>
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    setPendingDeleteDoc(doc)
                  }}
                  className="p-1 rounded hover:bg-destructive/10 hover:text-destructive opacity-0 group-hover:opacity-100 transition-all shrink-0 cursor-pointer"
                  title="Delete file"
                >
                  <Trash2 size={12} />
                </button>
              </motion.div>
            )
          })}

          {!isLoading && documents.length === 0 && (
            <div className="py-6 text-center italic text-muted-foreground/60 text-[10px] select-none">
              No files uploaded.
            </div>
          )}
        </div>
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
