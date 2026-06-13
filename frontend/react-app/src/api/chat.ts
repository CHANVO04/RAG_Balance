import { KGEvidenceInfo, SourceInfo } from '../store'
import { QueryMode } from '../store/searchStore'

export type SSEEventType =
  | { type: 'status';        step: string; substep: string }
  | { type: 'thought';       content: string }
  | { type: 'early_sources'; sources: SourceInfo[] }
  | { type: 'token';         content: string }
  | {
      type: 'done'
      kg_context?: string
      cached?: boolean
      answer?: string
      sources?: SourceInfo[]
      kg_sources?: KGEvidenceInfo[]
      retrieval_trace?: Record<string, unknown>
    }
  | { type: 'error';         message: string }

export async function streamChat(
  payload: {
    question: string
    conversation_id?: string | null
    workspace_id: string
    top_k: number
    qdrant_limit?: number
    score_threshold?: number
    max_context_chunks?: number
    temperature?: number
    max_input_tokens?: number
    max_output_tokens?: number
    custom_system_instruction?: string
    user_prompt_template?: string
    query_mode: QueryMode
    selected_files?: string[]
    use_cache?: boolean
  },
  onEvent: (event: SSEEventType) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

  const reader  = response.body!.getReader()
  const decoder = new TextDecoder()
  let remainder = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    remainder += decoder.decode(value, { stream: true })
    const lines = remainder.split('\n')
    remainder   = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const event = JSON.parse(line.slice(6)) as SSEEventType
        onEvent(event)
      } catch {
        // malformed JSON — skip
      }
    }
  }
}
