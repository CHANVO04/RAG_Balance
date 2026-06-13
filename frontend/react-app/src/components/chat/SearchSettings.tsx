import { FileText, GitBranch, Images, Lock, Maximize2, Sliders, Sparkles, Target, Thermometer, WalletCards, Zap } from 'lucide-react'
import { useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { cn } from '../../lib/utils'
import { fetchDocuments, fetchQueryDefaultPrompts } from '../../api/query'
import { DEFAULT_QUERY_MODE, DEFAULT_USER_PROMPT_TEMPLATE, QueryMode, useSearchStore } from '../../store/searchStore'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { useShallow } from 'zustand/react/shallow'
import { useStore } from '../../store'

const MODE_META: Record<QueryMode, {
  label: string
  description: string
  Icon: typeof Zap
  color: string
  visualFlow: string
  graphFlow: string
}> = {
  only_vector_fast: {
    label: 'Fast Search',
    description: 'Searches text and readable table text only. Skips image analysis and graph lookup to keep queries lightweight.',
    Icon: Target,
    color: 'text-primary',
    visualFlow: 'Skipped in Fast Search',
    graphFlow: 'Not used in this mode',
  },
  only_vector_multimodal: {
    label: 'Text + Visual Search',
    description: 'Searches document chunks and adds visual evidence when the question needs tables, formulas, or figures.',
    Icon: Images,
    color: 'text-emerald-500',
    visualFlow: 'Used when the question needs it',
    graphFlow: 'Not used in this mode',
  },
  hybrid: {
    label: 'Hybrid Search',
    description: 'Combines document chunks with graph relationships when the question needs connected concepts.',
    Icon: Zap,
    color: 'text-cyan-500',
    visualFlow: 'Used when the question needs it',
    graphFlow: 'Used when relationships help',
  },
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

export default function SearchSettings() {
  const { activeWorkspaceId, activeWorkspace } = useWorkspaceStore(
    useShallow((s) => ({
      activeWorkspaceId: s.activeWorkspaceId,
      activeWorkspace: s.workspaces.find((workspace) => workspace.id === s.activeWorkspaceId),
    }))
  )
  const { activeConversationId } = useStore()

  const setQdrantLimit = useSearchStore((s) => s.setQdrantLimit)
  const setScoreThreshold = useSearchStore((s) => s.setScoreThreshold)
  const setMaxContextChunks = useSearchStore((s) => s.setMaxContextChunks)
  const setTemperature = useSearchStore((s) => s.setTemperature)
  const setMaxInputTokens = useSearchStore((s) => s.setMaxInputTokens)
  const setMaxOutputTokens = useSearchStore((s) => s.setMaxOutputTokens)
  const setCustomSystemInstruction = useSearchStore((s) => s.setCustomSystemInstruction)
  const setUserPromptTemplate = useSearchStore((s) => s.setUserPromptTemplate)
  const setSelectedFiles = useSearchStore((s) => s.setSelectedFiles)
  const setUseCache = useSearchStore((s) => s.setUseCache)

  const documentsQuery = useQuery({
    queryKey: ['documents', activeWorkspaceId],
    queryFn: () => fetchDocuments(activeWorkspaceId),
    staleTime: 60_000,
  })
  const defaultPromptsQuery = useQuery({
    queryKey: ['query-default-prompts'],
    queryFn: fetchQueryDefaultPrompts,
    staleTime: 300_000,
  })

  // Direct reactive subscription to the active conversation settings using useShallow
  const settings = useSearchStore(
    useShallow((s) => s.getSettings(activeWorkspaceId, activeConversationId))
  )

  const strategy = activeWorkspace?.strategy ?? DEFAULT_QUERY_MODE
  const activeMode = MODE_META[strategy] ?? MODE_META[DEFAULT_QUERY_MODE]
  const ActiveIcon = activeMode.Icon
  const documents = documentsQuery.data ?? []
  const fileNames = useMemo(() => documents.map((doc) => doc.file_name).sort(), [documents])
  const selectedSet = useMemo(() => new Set(settings.selectedFiles), [settings.selectedFiles])
  const isAllFiles = settings.selectedFiles.length === 0

  useEffect(() => {
    if (!fileNames.length || !settings.selectedFiles.length) return
    const available = new Set(fileNames)
    const next = settings.selectedFiles.filter((fileName) => available.has(fileName))
    if (next.length !== settings.selectedFiles.length) {
      setSelectedFiles(activeWorkspaceId, activeConversationId, next)
    }
  }, [activeWorkspaceId, activeConversationId, fileNames, settings.selectedFiles, setSelectedFiles])

  const toggleFile = (fileName: string) => {
    const next = selectedSet.has(fileName)
      ? settings.selectedFiles.filter((selected) => selected !== fileName)
      : [...settings.selectedFiles, fileName]
    setSelectedFiles(activeWorkspaceId, activeConversationId, next)
  }

  return (
    <div className="rounded-2xl border border-border/60 bg-card p-4 shadow-premium">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Sliders size={16} className="text-primary" />
            <h3 className="text-xs font-black uppercase tracking-wider text-foreground">Query Settings</h3>
          </div>
          <p className="mt-1 text-[10px] font-semibold leading-relaxed text-muted-foreground">
            These controls are sent to the backend for the next chat request.
          </p>
        </div>
        <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-1 text-[9px] font-black uppercase tracking-wider text-primary">
          Live config
        </span>
      </div>

      <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-primary/10 bg-primary/5 p-3 text-[10px] font-semibold leading-relaxed text-muted-foreground">
        <Lock size={12} className="text-primary shrink-0 mt-0.5" />
        <span>
          Workspace strategy is locked after setup. Backend retrieval follows this workspace strategy, not per-query mode changes.
        </span>
      </div>

      <div className="mb-4 rounded-xl border border-primary/20 bg-accent/25 p-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-background border border-border/60">
            <ActiveIcon size={20} className={cn(activeMode.color)} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-black uppercase tracking-wider text-foreground">
                {activeMode.label}
              </span>
              <span className="rounded-md border border-primary/20 bg-primary/10 px-1.5 py-0.5 text-[8px] font-black uppercase tracking-wider text-primary">
                Workspace default
              </span>
            </div>
            <p className="mt-1 text-[10px] font-semibold leading-snug text-muted-foreground">
              {activeMode.description}
            </p>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-border/60 bg-background/60 p-2">
            <div className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-wider text-muted-foreground">
              <Images size={11} />
              Visual context
            </div>
            <div className="mt-1 text-[11px] font-bold">{activeMode.visualFlow}</div>
          </div>
          <div className="rounded-lg border border-border/60 bg-background/60 p-2">
            <div className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-wider text-muted-foreground">
              <GitBranch size={11} />
              Graph context
            </div>
            <div className="mt-1 text-[11px] font-bold">{activeMode.graphFlow}</div>
          </div>
        </div>
      </div>

      <div className="mb-4 rounded-xl border border-border/60 bg-background/40 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <FileText size={14} className="text-primary" />
            <span className="text-[10px] font-black uppercase tracking-wider">File scope</span>
          </div>
          <button
            onClick={() => setSelectedFiles(activeWorkspaceId, activeConversationId, [])}
            className={cn(
              'rounded-full px-2 py-1 text-[9px] font-black uppercase tracking-wider transition-colors',
              isAllFiles ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:text-foreground',
            )}
          >
            All documents
          </button>
        </div>
        {documentsQuery.isLoading ? (
          <div className="text-[10px] font-semibold text-muted-foreground">Loading workspace documents...</div>
        ) : fileNames.length ? (
          <div className="max-h-28 space-y-1 overflow-y-auto pr-1">
            {fileNames.map((fileName) => (
              <label
                key={fileName}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-[10px] font-semibold hover:bg-accent"
              >
                <input
                  type="checkbox"
                  checked={isAllFiles || selectedSet.has(fileName)}
                  onChange={() => toggleFile(fileName)}
                  className="h-3.5 w-3.5 accent-primary"
                />
                <span className="min-w-0 flex-1 truncate">{fileName}</span>
              </label>
            ))}
          </div>
        ) : (
          <div className="text-[10px] font-semibold text-muted-foreground">No ingested documents in this workspace.</div>
        )}
        <p className="mt-2 text-[10px] font-semibold leading-relaxed text-muted-foreground">
          Empty selection means the backend searches every document in the workspace.
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-3 rounded-xl border border-border/60 bg-background/40 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Qdrant limit</span>
            <input
              type="number"
              min={2}
              max={80}
              value={settings.qdrantLimit}
              onChange={(e) => setQdrantLimit(activeWorkspaceId, activeConversationId, clampNumber(Number(e.target.value) || 2, 2, 80))}
              className="w-14 rounded-lg border border-border bg-background px-2 py-1 text-center text-xs font-bold"
            />
          </div>
          <input
            type="range"
            min="2"
            max="80"
            value={settings.qdrantLimit}
            onChange={(e) => setQdrantLimit(activeWorkspaceId, activeConversationId, parseInt(e.target.value, 10))}
            className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-accent accent-primary"
          />
          <p className="text-[10px] font-semibold leading-relaxed text-muted-foreground">
            Number of Qdrant candidates retrieved before threshold filtering.
          </p>
        </div>

        <div className="space-y-3 rounded-xl border border-border/60 bg-background/40 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Score threshold</span>
            <input
              type="number"
              min={0}
              max={0.9}
              step={0.01}
              value={settings.scoreThreshold.toFixed(2)}
              onChange={(e) => setScoreThreshold(activeWorkspaceId, activeConversationId, clampNumber(Number(e.target.value) || 0, 0, 0.9))}
              className="w-16 rounded-lg border border-border bg-background px-2 py-1 text-center text-xs font-bold"
            />
          </div>
          <input
            type="range"
            min="0"
            max="0.9"
            step="0.01"
            value={settings.scoreThreshold}
            onChange={(e) => setScoreThreshold(activeWorkspaceId, activeConversationId, Number(e.target.value))}
            className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-accent accent-primary"
          />
          <p className="text-[10px] font-semibold leading-relaxed text-muted-foreground">
            If fewer than 2 chunks pass, backend falls back to top raw chunks.
          </p>
        </div>

        <div className="space-y-3 rounded-xl border border-border/60 bg-background/40 p-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Max context chunks</span>
            <input
              type="number"
              min={2}
              max={12}
              value={settings.maxContextChunks}
              onChange={(e) => setMaxContextChunks(activeWorkspaceId, activeConversationId, clampNumber(Number(e.target.value) || 2, 2, 12))}
              className="w-14 rounded-lg border border-border bg-background px-2 py-1 text-center text-xs font-bold"
            />
          </div>
          <input
            type="range"
            min="2"
            max="12"
            value={settings.maxContextChunks}
            onChange={(e) => setMaxContextChunks(activeWorkspaceId, activeConversationId, parseInt(e.target.value, 10))}
            className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-accent accent-primary"
          />
          <p className="text-[10px] font-semibold leading-relaxed text-muted-foreground">
            Final document chunks allowed in the LLM prompt. Backend clamps this to 2-12.
          </p>
        </div>

        <div className="space-y-3 rounded-xl border border-border/60 bg-background/40 p-3">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wider text-muted-foreground">
              <Thermometer size={12} />
              Temperature
            </span>
            <input
              type="number"
              min={0}
              max={0.7}
              step={0.05}
              value={settings.temperature.toFixed(2)}
              onChange={(e) => setTemperature(activeWorkspaceId, activeConversationId, clampNumber(Number(e.target.value) || 0, 0, 0.7))}
              className="w-16 rounded-lg border border-border bg-background px-2 py-1 text-center text-xs font-bold"
            />
          </div>
          <input
            type="range"
            min="0"
            max="0.7"
            step="0.05"
            value={settings.temperature}
            onChange={(e) => setTemperature(activeWorkspaceId, activeConversationId, Number(e.target.value))}
            className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-accent accent-primary"
          />
          <p className="text-[10px] font-semibold leading-relaxed text-muted-foreground">
            Controls answer randomness. Backend clamps this to 0.0-0.7.
          </p>
        </div>

        <div className="xl:col-span-2 space-y-3 rounded-xl border border-border/60 bg-background/40 p-3">
          <label className="flex cursor-pointer items-center justify-between">
            <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Use Semantic Cache</span>
            <input
              type="checkbox"
              checked={settings.useCache}
              onChange={(e) => setUseCache(activeWorkspaceId, activeConversationId, e.target.checked)}
              className="h-4 w-4 rounded border-border bg-background accent-primary cursor-pointer"
            />
          </label>
          <p className="text-[10px] font-semibold leading-relaxed text-muted-foreground">
            Bypass the cache when disabled to compare query configuration changes for identical questions.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <div className="rounded-xl border border-border/60 bg-background/40 p-3">
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wider text-muted-foreground">
              <WalletCards size={12} />
              Max input tokens
            </span>
            <input
              type="number"
              min={2048}
              max={16000}
              step={512}
              value={settings.maxInputTokens}
              onChange={(e) => setMaxInputTokens(activeWorkspaceId, activeConversationId, clampNumber(Number(e.target.value) || 2048, 2048, 16000))}
              className="w-24 rounded-lg border border-border bg-background px-2 py-1 text-center text-xs font-bold"
            />
          </div>
          <input
            type="range"
            min="2048"
            max="16000"
            step="512"
            value={settings.maxInputTokens}
            onChange={(e) => setMaxInputTokens(activeWorkspaceId, activeConversationId, parseInt(e.target.value, 10))}
            className="mt-3 h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-accent accent-primary"
          />
          <p className="mt-3 flex items-start gap-1.5 text-[10px] font-semibold leading-relaxed text-muted-foreground">
            <Sparkles size={12} className="mt-0.5 shrink-0 text-primary" />
            Caps the prompt context sent to the LLM before generation. Backend enforces 2048-16000.
          </p>
        </div>

        <div className="rounded-xl border border-border/60 bg-background/40 p-3">
        <div className="flex items-center justify-between gap-3">
          <span className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wider text-muted-foreground">
            <Maximize2 size={12} />
            Max output tokens
          </span>
          <input
            type="number"
            min={256}
            max={2048}
            step={128}
            value={settings.maxOutputTokens}
            onChange={(e) => setMaxOutputTokens(activeWorkspaceId, activeConversationId, clampNumber(Number(e.target.value) || 256, 256, 2048))}
            className="w-20 rounded-lg border border-border bg-background px-2 py-1 text-center text-xs font-bold"
          />
        </div>
        <input
          type="range"
          min="256"
          max="2048"
          step="128"
          value={settings.maxOutputTokens}
          onChange={(e) => setMaxOutputTokens(activeWorkspaceId, activeConversationId, parseInt(e.target.value, 10))}
          className="mt-3 h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-accent accent-primary"
        />
        <p className="mt-3 flex items-start gap-1.5 text-[10px] font-semibold leading-relaxed text-muted-foreground">
          <Sparkles size={12} className="mt-0.5 shrink-0 text-primary" />
          This affects generation cost and answer length. It does not change which chunks are retrieved.
        </p>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-border/60 bg-background/40 p-3">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Prompt configuration</div>
            <p className="mt-1 text-[10px] font-semibold leading-relaxed text-muted-foreground">
              Review the default prompts first, then add lightweight overrides for the next question.
            </p>
          </div>
          <button
            onClick={() => {
              setCustomSystemInstruction(activeWorkspaceId, activeConversationId, '')
              setUserPromptTemplate(activeWorkspaceId, activeConversationId, DEFAULT_USER_PROMPT_TEMPLATE)
            }}
            className="rounded-full bg-muted px-2 py-1 text-[9px] font-black uppercase tracking-wider text-muted-foreground hover:text-foreground"
          >
            Reset
          </button>
        </div>

        <div className="mb-3 space-y-2">
          {defaultPromptsQuery.isLoading ? (
            <div className="rounded-xl bg-muted/30 p-3 text-[10px] font-semibold text-muted-foreground">
              Loading default prompts from the backend...
            </div>
          ) : defaultPromptsQuery.isError ? (
            <div className="rounded-xl bg-red-500/10 p-3 text-[10px] font-semibold text-red-500">
              Default prompts could not be loaded from the backend.
            </div>
          ) : (
            <>
              <details className="rounded-xl border border-border/60 bg-card p-2">
                <summary className="cursor-pointer text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                  Default system prompt used by the app
                </summary>
                <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-background/80 p-2 text-[10px] leading-relaxed text-foreground/80">
                  {defaultPromptsQuery.data?.system_prompt}
                </pre>
              </details>
              <details className="rounded-xl border border-border/60 bg-card p-2">
                <summary className="cursor-pointer text-[10px] font-black uppercase tracking-wider text-muted-foreground">
                  Default user prompt template
                </summary>
                <pre className="mt-2 max-h-36 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-background/80 p-2 font-mono text-[10px] leading-relaxed text-foreground/80">
                  {defaultPromptsQuery.data?.user_prompt_template}
                </pre>
              </details>
            </>
          )}
        </div>

        <label className="block">
          <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Additional answer instruction</span>
          <textarea
            value={settings.customSystemInstruction}
            onChange={(e) => setCustomSystemInstruction(activeWorkspaceId, activeConversationId, e.target.value)}
            placeholder="Example: Answer for a thesis defense audience. Be concise, explain uncertainty, and use bullet points when helpful."
            rows={3}
            maxLength={4000}
            className="mt-2 w-full resize-y rounded-xl border border-border bg-card px-3 py-2 text-xs leading-relaxed outline-none focus:border-primary"
          />
        </label>
        <p className="mt-2 text-[10px] font-semibold leading-relaxed text-muted-foreground">
          This is appended after the default system prompt. It cannot override citation and grounding rules.
        </p>

        <label className="mt-3 block">
          <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">Custom user prompt template</span>
          <textarea
            value={settings.userPromptTemplate}
            onChange={(e) => setUserPromptTemplate(activeWorkspaceId, activeConversationId, e.target.value)}
            rows={4}
            maxLength={8000}
            className="mt-2 w-full resize-y rounded-xl border border-border bg-card px-3 py-2 font-mono text-[10px] leading-relaxed outline-none focus:border-primary"
          />
        </label>
        <p className="mt-2 text-[10px] font-semibold leading-relaxed text-muted-foreground">
          Template must include <code className="rounded bg-muted px-1">{'{context}'}</code> and <code className="rounded bg-muted px-1">{'{question}'}</code>. If either is missing, the backend falls back to the default prompt shape.
        </p>
      </div>
    </div>
  )
}
