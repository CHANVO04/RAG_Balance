import {
  formatDuration,
  getIngestTimingSummary,
  type IngestTimingSnapshot,
} from './ingestTiming'

const activeSnapshot: IngestTimingSnapshot = {
  startedAt: 1_000,
  uploadedAt: 3_500,
  estimatedMinutes: 9,
}

const completedSnapshot: IngestTimingSnapshot = {
  ...activeSnapshot,
  readyAt: 184_000,
}

if (formatDuration(125_000) !== '2m 05s') {
  throw new Error('formatDuration should render minutes and padded seconds.')
}

if (getIngestTimingSummary(activeSnapshot, 64_000) !== 'Upload 2.5s · Total 1m 03s · ETA ~9m') {
  throw new Error('active ingest summary should include upload, total elapsed, and ETA.')
}

if (getIngestTimingSummary(completedSnapshot, 200_000) !== 'Ready in 3m 03s · Upload 2.5s') {
  throw new Error('completed ingest summary should freeze at readyAt and show upload duration.')
}
