import type { SourceInfo } from '../store'

export type EvidenceKind = 'text' | 'table' | 'image' | 'formula'

export interface SourceGuidance {
  kind: EvidenceKind
  label: string
  lookFor: string
  guidance: string
}

export function sourceBadge(sourceId: number) {
  return `S${String(Math.max(0, sourceId)).padStart(3, '0').slice(-3)}`
}

export function sourceRef(source?: SourceInfo, fallbackId?: number | string) {
  if (source?.ref_id) return source.ref_id
  if (source?.citation_id) return source.citation_id
  if (typeof fallbackId === 'string' && fallbackId.trim()) return fallbackId.trim()
  if (typeof fallbackId === 'number') return sourceBadge(fallbackId)
  return ''
}

export function sourcePage(source?: SourceInfo) {
  const page = Number(source?.page)
  return Number.isFinite(page) && page > 0 ? page : 1
}

export function isSameSource(a?: SourceInfo | null, b?: SourceInfo | null) {
  if (!a || !b) return false
  const aRef = sourceRef(a, a.id)
  const bRef = sourceRef(b, b.id)
  if (aRef && bRef) return aRef === bRef
  return a.id === b.id && a.file_name === b.file_name
}

export function sourceGuidance(source: SourceInfo): SourceGuidance {
  const explicitKind = source.kind
  const sectionLabel = source.section_label.toLowerCase()

  if (explicitKind === 'text') {
    return {
      kind: 'text',
      label: 'Text evidence',
      lookFor: source.section_label || `the cited passage on page ${sourcePage(source)}`,
      guidance: 'Use this source to compare the answer with the surrounding paragraph in the original document.',
    }
  }

  if (explicitKind === 'table' || (!explicitKind && (source.has_table || sectionLabel.includes('table')))) {
    return {
      kind: 'table',
      label: 'Table evidence',
      lookFor: source.section_label || `a table on page ${sourcePage(source)}`,
      guidance: 'Use this source to verify numeric values, rows, columns, and table captions in the original paper.',
    }
  }

  if (explicitKind === 'image' || (!explicitKind && (source.has_image || sectionLabel.includes('image')))) {
    return {
      kind: 'image',
      label: 'Figure evidence',
      lookFor: source.section_label || `a figure or image on page ${sourcePage(source)}`,
      guidance: 'Use this source to inspect the figure, caption, plotted trend, and surrounding explanation in the original paper.',
    }
  }

  if (explicitKind === 'formula' || (!explicitKind && (source.has_formula || sectionLabel.includes('formula')))) {
    return {
      kind: 'formula',
      label: 'Formula evidence',
      lookFor: source.section_label || `a formula on page ${sourcePage(source)}`,
      guidance: 'Use this source to verify the equation, symbols, and the nearby derivation or explanation.',
    }
  }

  return {
    kind: 'text',
    label: 'Text evidence',
    lookFor: source.section_label || `the cited passage on page ${sourcePage(source)}`,
    guidance: 'Use this source to compare the answer with the surrounding paragraph in the original document.',
  }
}

export function formatRelevance(score?: number | string | null): number {
  if (score === undefined || score === null) return 0
  const num = Number(score)
  if (Number.isNaN(num)) return 0
  
  // If it's a standard Qdrant similarity score (already between 0 and 1)
  if (num >= 0 && num <= 1) {
    return Math.round(num * 100)
  }
  
  // If it's a Cross-Encoder logit score (which can be negative or > 1)
  // Apply a sigmoid mapping centered around -5.0 with temperature scaling
  const sigmoid = 1 / (1 + Math.exp(-(num + 5.0) / 2.5))
  return Math.round(sigmoid * 100)
}
