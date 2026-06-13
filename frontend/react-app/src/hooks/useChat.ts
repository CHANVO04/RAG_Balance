import { useRef, useState } from 'react'
import { streamChat } from '../api/chat'
import { processToken, flushBuffer, FSMState, Segment } from '../lib/streamBuffer'
import { appendMergedSegments, mergeAdjacentTextSegments } from '../lib/messageSegments'
import { useStore, AgentStep, KGEvidenceInfo, Message, SourceInfo } from '../store'
import { useWorkspaceStore } from '../store/workspaceStore'
import { DEFAULT_QUERY_MODE, useSearchStore } from '../store/searchStore'
import { useToastStore } from '../store/toastStore'

const stepOrder = ['analyzing', 'retrieving', 'generating'] as const

function makeInitialSteps(now: number): AgentStep[] {
  return [
    { id: 'analyzing', label: 'Analyzing', status: 'running', startedAt: now },
    { id: 'retrieving', label: 'Retrieving', status: 'pending' },
    { id: 'generating', label: 'Synthesizing', status: 'pending' },
  ]
}

function normalizeStatusText(text: string) {
  const lower = text.toLowerCase()
  if (lower.includes('tìm') || lower.includes('search') || lower.includes('retriev') || lower.includes('kg') || lower.includes('vector')) return 'Retrieving evidence'
  if (lower.includes('tạo') || lower.includes('tổng hợp') || lower.includes('generat') || lower.includes('synthes')) return 'Synthesizing answer'
  if (lower.includes('lỗi') || lower.includes('error')) return 'Error'
  return 'Analyzing request'
}

function advanceSteps(steps: AgentStep[], activeId: string, now: number): AgentStep[] {
  const activeIndex = stepOrder.indexOf(activeId as (typeof stepOrder)[number])
  return steps.map((step) => {
    const index = stepOrder.indexOf(step.id as (typeof stepOrder)[number])
    if (index < activeIndex && step.status !== 'completed') {
      const startedAt = step.startedAt ?? now
      return { ...step, status: 'completed', completedAt: now, duration: Math.max(0.1, (now - startedAt) / 1000) }
    }
    if (step.id === activeId) {
      return { ...step, status: 'running', startedAt: step.startedAt ?? now }
    }
    return step
  })
}

function completeSteps(steps: AgentStep[], now: number): AgentStep[] {
  return steps.map((step) => {
    const startedAt = step.startedAt ?? now
    return step.status === 'completed'
      ? step
      : { ...step, status: 'completed', completedAt: now, duration: Math.max(0.1, (now - startedAt) / 1000) }
  })
}

function failSteps(steps: AgentStep[]): AgentStep[] {
  return steps.map((step) => step.status === 'running' ? { ...step, status: 'error' } : step)
}

export function useChat() {
  const {
    activeConversationId,
    addMessage,
    updateMessage,
    setSources,
    clearActiveSource,
  } = useStore()
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const activeWorkspaceStrategy = useWorkspaceStore((s) => (
    s.workspaces.find((workspace) => workspace.id === s.activeWorkspaceId)?.strategy ?? DEFAULT_QUERY_MODE
  ))
  const getSettings = useSearchStore((s) => s.getSettings)
  const pushToast = useToastStore((s) => s.pushToast)
  const [isStreaming, setIsStreaming] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  const sendMessage = async (question: string) => {
    if (isStreaming || !activeConversationId) return

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      segments: [{ type: 'text', content: question }],
      sources: [],
    }
    const assistantId = crypto.randomUUID()
    const now = performance.now()
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      segments: [],
      sources: [],
      thought: 'Preparing research trace...',
      thinkingComplete: false,
      steps: makeInitialSteps(now),
      isStreaming: true,
    }

    addMessage(userMsg)
    addMessage(assistantMsg)
    clearActiveSource()
    setSources([])
    setIsStreaming(true)
    setStatusMsg('Analyzing request')

    const controller = new AbortController()
    abortRef.current = controller

    let fsmState: FSMState = 'normal'
    let fsmBuf = ''
    let accSegments: Segment[] = []
    let msgSources: SourceInfo[] = []
    let msgKgSources: KGEvidenceInfo[] = []
    let msgRetrievalTrace: Record<string, unknown> | undefined
    const search = getSettings(activeWorkspaceId, activeConversationId)

    try {
      await streamChat(
        {
          question,
          conversation_id: activeConversationId,
          workspace_id: activeWorkspaceId,
          top_k: search.qdrantLimit,
          qdrant_limit: search.qdrantLimit,
          score_threshold: search.scoreThreshold,
          max_context_chunks: search.maxContextChunks,
          temperature: search.temperature,
          max_input_tokens: search.maxInputTokens,
          max_output_tokens: search.maxOutputTokens,
          custom_system_instruction: search.customSystemInstruction,
          user_prompt_template: search.userPromptTemplate,
          query_mode: activeWorkspaceStrategy,
          selected_files: search.selectedFiles,
          use_cache: search.useCache,
        },
        (event) => {
          if (event.type === 'status') {
            const normalizedStep = normalizeStatusText(event.step)
            const stepText = [normalizedStep, event.substep].filter(Boolean).join(' - ')
            setStatusMsg(normalizedStep)
            updateMessage(assistantId, (msg) => {
              const step = event.step.toLowerCase()
              const activeStep = step.includes('tạo') || step.includes('tổng hợp') || step.includes('generat') || step.includes('synthes')
                ? 'generating'
                : step.includes('tìm') || step.includes('kg') || step.includes('vector') || step.includes('search') || step.includes('retriev')
                  ? 'retrieving'
                  : 'analyzing'
              return {
                ...msg,
                thought: `${msg.thought ? `${msg.thought}\n` : ''}${stepText}`,
                thinkingComplete: activeStep === 'generating' ? true : msg.thinkingComplete,
                steps: advanceSteps(msg.steps ?? makeInitialSteps(performance.now()), activeStep, performance.now()),
              }
            })
          } else if (event.type === 'thought') {
            updateMessage(assistantId, (msg) => ({
              ...msg,
              thought: `${msg.thought ? `${msg.thought}\n` : ''}${event.content}`,
            }))
          } else if (event.type === 'early_sources') {
            msgSources = event.sources
            setSources(event.sources)
            updateMessage(assistantId, (msg) => ({ ...msg, sources: event.sources }))
          } else if (event.type === 'token') {
            const { segments, newState, newBuf } = processToken(event.content, fsmState, fsmBuf)
            fsmState = newState
            fsmBuf = newBuf
            accSegments = appendMergedSegments(accSegments, segments)
            updateMessage(assistantId, (msg) => ({
              ...msg,
              segments: accSegments,
              sources: msgSources,
              thinkingComplete: true,
            }))
          } else if (event.type === 'done') {
            const remaining = flushBuffer(fsmState, fsmBuf)
            accSegments = appendMergedSegments(accSegments, remaining)
            if (event.cached && event.answer) {
              accSegments = [{ type: 'text', content: event.answer }]
            }
            const finalSources = event.sources ?? msgSources
            msgKgSources = event.kg_sources ?? []
            msgRetrievalTrace = event.retrieval_trace
            setSources(finalSources)
            updateMessage(assistantId, (msg) => ({
              ...msg,
              segments: mergeAdjacentTextSegments(accSegments),
              sources: finalSources,
              kgSources: msgKgSources,
              retrievalTrace: msgRetrievalTrace,
              thinkingComplete: true,
              steps: completeSteps(msg.steps ?? [], performance.now()),
              isStreaming: false,
            }))
          } else if (event.type === 'error') {
            pushToast({ type: 'error', title: 'Chat request failed', description: event.message })
            updateMessage(assistantId, (msg) => ({
              ...msg,
              segments: [{ type: 'text', content: `Error: ${event.message}` }],
              sources: [],
              thinkingComplete: true,
              steps: failSteps(msg.steps ?? []),
              isStreaming: false,
            }))
          }
        },
        controller.signal,
      )
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        pushToast({ type: 'error', title: 'Connection error', description: (err as Error).message })
        updateMessage(assistantId, (msg) => ({
          ...msg,
          segments: [{ type: 'text', content: `Connection error: ${(err as Error).message}` }],
          sources: [],
          steps: failSteps(msg.steps ?? []),
          isStreaming: false,
        }))
      } else {
        pushToast({ type: 'info', title: 'Request cancelled' })
        updateMessage(assistantId, (msg) => ({
          ...msg,
          thought: `${msg.thought ? `${msg.thought}\n` : ''}The operation was cancelled.`,
          thinkingComplete: true,
          isStreaming: false,
        }))
      }
    } finally {
      setIsStreaming(false)
      setStatusMsg('')
      abortRef.current = null
    }
  }

  const abort = () => abortRef.current?.abort()

  return { sendMessage, isStreaming, statusMsg, abort }
}
