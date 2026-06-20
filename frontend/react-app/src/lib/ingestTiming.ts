export interface IngestTimingSnapshot {
  startedAt?: number
  uploadedAt?: number
  readyAt?: number
  endedAt?: number
  backendElapsedMs?: number
  stageTimingsMs?: Record<string, Record<string, number>>
  outcome?: 'ready' | 'error'
  estimatedMinutes?: number
}

function clampDuration(ms: number) {
  return Math.max(0, Math.floor(ms))
}

export function formatDuration(ms: number) {
  const safeMs = clampDuration(ms)
  const totalSeconds = Math.floor(safeMs / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  const milliseconds = safeMs % 1000
  if (minutes <= 0) {
    return `${seconds}.${milliseconds.toString().padStart(3, '0')}s`
  }
  return `${minutes}m ${seconds.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')}s`
}

function formatUploadDuration(startedAt?: number, uploadedAt?: number) {
  if (!startedAt || !uploadedAt) {
    return ''
  }
  const seconds = clampDuration(uploadedAt - startedAt) / 1000
  return `Upload ${seconds.toFixed(1)}s`
}

export function getIngestTimingSummary(snapshot: IngestTimingSnapshot, now: number) {
  if (!snapshot.startedAt) {
    return ''
  }

  const uploadText = formatUploadDuration(snapshot.startedAt, snapshot.uploadedAt)
  const finishedAt = snapshot.readyAt || snapshot.endedAt
  if (finishedAt) {
    const label = snapshot.outcome === 'error' ? 'Stopped after' : 'Ready in'
    const measuredMs = snapshot.backendElapsedMs ?? finishedAt - snapshot.startedAt
    const backendText = snapshot.backendElapsedMs !== undefined ? `Backend ${formatDuration(snapshot.backendElapsedMs)}` : ''
    return [`${label} ${formatDuration(measuredMs)}`, uploadText, backendText]
      .filter(Boolean)
      .join(' · ')
  }

  const totalText = `Running ${formatDuration(now - snapshot.startedAt)}`
  return [uploadText || 'Uploading...', totalText].filter(Boolean).join(' · ')
}
