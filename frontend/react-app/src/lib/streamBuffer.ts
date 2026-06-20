export type FSMState = 'normal' | 'latex_inline' | 'latex_block' | 'cite'
export type SegmentType = 'text' | 'latex_inline' | 'latex_block' | 'cite' | 'kg_cite'
export interface Segment { type: SegmentType; content: string }

export interface FSMResult {
  segments: Segment[]
  newState: FSMState
  newBuf: string
}

function isCitationStart(ch: string, next: string) {
  return ch === '[' && /[A-Za-z0-9]/.test(next)
}

function normalizeCitation(content: string): Segment | null {
  const trimmed = content.trim()
  const kgMatch = trimmed.match(/^KG-(\d{1,3})$/i)
  if (kgMatch) {
    return { type: 'kg_cite', content: `KG-${kgMatch[1].padStart(2, '0')}` }
  }

  // Accept both compact citations and user-facing labels emitted by the LLM.
  const refMatch = trimmed.match(/^(?:Ref\s+)?(\d+|[a-z0-9]{4})$/i)
  if (refMatch) return { type: 'cite', content: refMatch[1] }

  const visualMatch = trimmed.match(/^(?:(?:Table|Fig\.?|Figure|Eq\.?|Equation)\s+)?((?:IMG|FORM|TBL)-[a-z0-9]{4})$/i)
  if (visualMatch) return { type: 'cite', content: visualMatch[1] }

  return null
}

export function processToken(
  incoming: string,
  state: FSMState,
  buf: string,
): FSMResult {
  const segments: Segment[] = []
  const s = buf + incoming

  let cur = ''
  let st  = state
  let pos = 0

  while (pos < s.length) {
    const ch   = s[pos]
    const next = s[pos + 1] ?? ''

    if (st === 'normal') {
      if (ch === '$' && next === '$') {
        if (cur) { segments.push({ type: 'text', content: cur }); cur = '' }
        st  = 'latex_block'
        pos += 2
        continue
      }
      if (ch === '$') {
        if (cur) { segments.push({ type: 'text', content: cur }); cur = '' }
        st  = 'latex_inline'
        pos += 1
        continue
      }
      if (isCitationStart(ch, next)) {
        if (cur) { segments.push({ type: 'text', content: cur }); cur = '' }
        st  = 'cite'
        pos += 1
        continue
      }
      cur += ch
      pos += 1

    } else if (st === 'latex_inline') {
      if (ch === '$') {
        segments.push({ type: 'latex_inline', content: cur })
        cur = ''; st = 'normal'; pos += 1
      } else {
        cur += ch; pos += 1
      }

    } else if (st === 'latex_block') {
      if (ch === '$' && next === '$') {
        segments.push({ type: 'latex_block', content: cur })
        cur = ''; st = 'normal'; pos += 2
      } else {
        cur += ch; pos += 1
      }

    } else if (st === 'cite') {
      if (ch === ']') {
        const citation = normalizeCitation(cur)
        if (citation) {
          segments.push(citation)
        } else {
          segments.push({ type: 'text', content: `[${cur}]` })
        }
        cur = ''; st = 'normal'; pos += 1
      } else if (cur.length > 16 || ch === '\n') {
        segments.push({ type: 'text', content: `[${cur}${ch}` })
        cur = ''; st = 'normal'; pos += 1
      } else {
        cur += ch; pos += 1
      }
    }
  }

  if (st === 'normal' && cur) {
    const hasPendingCitationStart = cur.endsWith('[')
    const text = hasPendingCitationStart ? cur.slice(0, -1) : cur
    if (text) segments.push({ type: 'text', content: text })
    return { segments, newState: st, newBuf: hasPendingCitationStart ? '[' : '' }
  }

  return { segments, newState: st, newBuf: cur }
}

/** Call at end of stream to flush any remaining buffer */
export function flushBuffer(state: FSMState, buf: string): Segment[] {
  if (!buf) return []
  if (state === 'cite') {
    return [{ type: 'text', content: `[${buf}` }]
  }
  const type: SegmentType =
    state === 'normal'       ? 'text'
    : state === 'latex_inline' ? 'latex_inline'
    : state === 'latex_block'  ? 'latex_block'
    : 'text'
  return [{ type, content: buf }]
}
