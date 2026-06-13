import { useState } from 'react'
import { Microscope, Brain, BookOpen, FileText, Cpu, Network, Check, Target, Images, Zap, X } from 'lucide-react'
import { QueryMode, useSearchStore } from '../../store/searchStore'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { createWorkspaceRemote, deleteWorkspaceRemote, updateWorkspaceRemote } from '../../api/workspaces'
import { useToastStore } from '../../store/toastStore'
import { cn } from '../../lib/utils'
import { motion } from 'framer-motion'

const ICON_OPTIONS = [
  { id: 'Microscope', icon: Microscope, label: 'Science', emoji: '🔬', color: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/30' },
  { id: 'Brain', icon: Brain, label: 'AI & ML', emoji: '🧠', color: 'text-purple-500 bg-purple-500/10 border-purple-500/30' },
  { id: 'BookOpen', icon: BookOpen, label: 'Literature', emoji: '📚', color: 'text-blue-500 bg-blue-500/10 border-blue-500/30' },
  { id: 'FileText', icon: FileText, label: 'Technical', emoji: '📄', color: 'text-amber-500 bg-amber-500/10 border-amber-500/30' },
  { id: 'Cpu', icon: Cpu, label: 'Hardware', emoji: '⚡', color: 'text-rose-500 bg-rose-500/10 border-rose-500/30' },
  { id: 'Network', icon: Network, label: 'Telecom', emoji: '📡', color: 'text-cyan-500 bg-cyan-500/10 border-cyan-500/30' },
]

// Custom friendly logo: intersecting node rings joined by a friendly, clean link
function NexusLogo() {
  return (
    <div className="inline-flex p-2.5 rounded-2xl bg-gradient-to-tr from-primary/10 to-cyan-500/10 text-primary mb-2 shadow-sm border border-primary/20 wizard-logo-container">
      <svg width="36" height="36" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-10 h-10">
        <rect x="2" y="2" width="36" height="36" rx="10" fill="url(#bgGrad)" stroke="url(#borderGrad)" strokeWidth="1.5" />
        <circle cx="14" cy="20" r="5" stroke="#2563eb" strokeWidth="2.5" fill="none" />
        <circle cx="26" cy="20" r="5" stroke="#06b6d4" strokeWidth="2.5" fill="none" />
        <path d="M14 20C17 17 23 23 26 20" stroke="url(#lineGrad)" strokeWidth="2.5" strokeLinecap="round" />
        <circle cx="14" cy="20" r="1.5" fill="#2563eb" />
        <circle cx="26" cy="20" r="1.5" fill="#06b6d4" />
        <defs>
          <linearGradient id="bgGrad" x1="2" y1="2" x2="38" y2="38" gradientUnits="userSpaceOnUse">
            <stop stopColor="rgba(37, 99, 235, 0.05)" />
            <stop offset="1" stopColor="rgba(6, 182, 212, 0.05)" />
          </linearGradient>
          <linearGradient id="borderGrad" x1="2" y1="2" x2="38" y2="38" gradientUnits="userSpaceOnUse">
            <stop stopColor="rgba(37, 99, 235, 0.2)" />
            <stop offset="1" stopColor="rgba(6, 182, 212, 0.2)" />
          </linearGradient>
          <linearGradient id="lineGrad" x1="14" y1="20" x2="26" y2="20" gradientUnits="userSpaceOnUse">
            <stop stopColor="#2563eb" />
            <stop offset="1" stopColor="#06b6d4" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  )
}

export default function WorkspaceSetupWizard() {
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const removeWorkspace = useWorkspaceStore((s) => s.removeWorkspace)
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const updateWorkspace = useWorkspaceStore((s) => s.updateWorkspace)
  const setMode = useSearchStore((s) => s.setMode)
  const setTopK = useSearchStore((s) => s.setTopK)
  const pushToast = useToastStore((s) => s.pushToast)

  const hasCompletedWorkspace = workspaces.some((w) => w.isSetupComplete && w.id !== activeWorkspaceId)

  const handleCancel = async () => {
    if (!hasCompletedWorkspace) return
    try {
      await deleteWorkspaceRemote(activeWorkspaceId)
    } catch (err) {
      console.warn('Failed to delete cancelled workspace from backend:', err)
    } finally {
      removeWorkspace(activeWorkspaceId)
    }
  }

  // Empty string default to require user inputs with placeholder
  const [workspaceName, setWorkspaceName] = useState('')
  const [selectedIconId, setSelectedIconId] = useState('Microscope')
  const [selectedStrategy, setSelectedStrategy] = useState<QueryMode | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const selectedOption = ICON_OPTIONS.find((o) => o.id === selectedIconId) || ICON_OPTIONS[0]

  const strategies: { id: QueryMode; label: string; tagline: string; description: string; icon: typeof Target; accent: string; ringColor: string; bgGlow: string }[] = [
    {
      id: 'only_vector_fast',
      label: 'Basic Text',
      tagline: 'Just search the text',
      description: 'Fast, simple, and straightforward. Skips images and complex equations to give you quick answers from the text.',
      icon: Target,
      accent: 'border-primary text-primary bg-primary/5',
      ringColor: 'ring-primary/25',
      bgGlow: 'from-blue-600/10 to-transparent',
    },
    {
      id: 'only_vector_multimodal',
      label: 'Formulas & Visuals',
      tagline: 'Read math and diagrams',
      description: 'Scans and understands charts, math equations, and figures alongside the text. Best for science and engineering papers.',
      icon: Images,
      accent: 'border-emerald-500 text-emerald-500 bg-emerald-500/5',
      ringColor: 'ring-emerald-500/25',
      bgGlow: 'from-emerald-600/10 to-transparent',
    },
    {
      id: 'hybrid',
      label: 'Complex Questions',
      tagline: 'Connect multiple papers',
      description: 'Links concepts, citations, and papers together. Choose this when you are doing deep comparative research or asking multi-hop questions.',
      icon: Zap,
      accent: 'border-cyan-500 text-cyan-500 bg-cyan-500/5',
      ringColor: 'ring-cyan-500/25',
      bgGlow: 'from-cyan-600/10 to-transparent',
    },
  ]

  const handleStart = async () => {
    if (!selectedStrategy || !activeWorkspaceId || !workspaceName.trim()) return
    const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId)
    if (!activeWorkspace) return

    const updates = {
      name: workspaceName.trim(),
      icon: selectedOption.emoji,
      strategy: selectedStrategy,
      isSetupComplete: true,
    }
    const remoteWorkspace = {
      id: activeWorkspace.id,
      name: updates.name,
      strategy: selectedStrategy,
      icon: updates.icon,
      collectionName: activeWorkspace.collectionName,
      systemPrompt: activeWorkspace.systemPrompt,
      createdAt: activeWorkspace.createdAt,
      isSetupComplete: true,
    }

    setIsSaving(true)
    try {
      try {
        await updateWorkspaceRemote(activeWorkspace.id, remoteWorkspace)
      } catch (err) {
        if (!(err as Error).message.includes('HTTP 404')) throw err
        await createWorkspaceRemote(remoteWorkspace)
      }

      // Save to the active workspace settings only after backend registry is synced.
      updateWorkspace(activeWorkspaceId, updates)

      // Sync search store with defaults
      setMode(activeWorkspaceId, null, selectedStrategy)
      setTopK(activeWorkspaceId, null, 5)
    } catch (err) {
      console.error('Failed to save workspace setup:', err)
      pushToast({ type: 'error', title: 'Workspace setup failed', description: (err as Error).message })
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="flex-1 flex items-start justify-center p-4 sm:p-6 h-full overflow-y-auto bg-background relative">
      {/* Background radial reflections matching premium theme */}
      <div className="absolute inset-0 pointer-events-none z-0">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full bg-primary/10 blur-[100px] animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] rounded-full bg-cyan-500/5 blur-[120px]" />
      </div>

      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className="max-w-5xl w-full p-6 sm:p-8 rounded-3xl glass border border-slate-200/80 dark:border-border/50 shadow-2xl relative z-10 flex flex-col gap-4 sm:gap-5 wizard-card my-auto"
      >
        {/* Absolute cancel X button */}
        {hasCompletedWorkspace && (
          <button
            type="button"
            onClick={handleCancel}
            className="absolute top-4 right-4 p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 z-20"
            title="Cancel workspace creation"
          >
            <X size={20} />
          </button>
        )}
        {/* Title Block */}
        <div className="text-center space-y-1.5">
          <NexusLogo />
          <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-900 dark:text-white">Configure Your Workspace</h1>
          <p className="text-xs sm:text-sm font-bold text-slate-700 dark:text-slate-300 max-w-2xl mx-auto leading-relaxed wizard-subtitle">
            Name your new workspace, pick a style icon, and select a default search strategy.
          </p>
        </div>

        {/* Workspace Name Input - Empty by default with custom placeholder */}
        <div className="space-y-1.5">
          <label className="text-xs sm:text-[13px] font-extrabold uppercase tracking-wider text-slate-900 dark:text-slate-100 block">Workspace Name</label>
          <input
            type="text"
            value={workspaceName}
            onChange={(e) => setWorkspaceName(e.target.value)}
            placeholder="Please enter your workspace name here..."
            className="w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-border/80 bg-background/50 focus:bg-background focus:ring-2 focus:ring-primary/25 focus:border-primary/50 text-sm font-bold transition-all text-slate-900 dark:text-white shadow-sm wizard-input"
          />
        </div>

        {/* Labeled Workspace Icon Grid */}
        <div className="space-y-1.5">
          <label className="text-xs sm:text-[13px] font-extrabold uppercase tracking-wider text-slate-900 dark:text-slate-100 block">Workspace Icon</label>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            {ICON_OPTIONS.map((opt) => {
              const OptIcon = opt.icon
              const isSelected = selectedIconId === opt.id
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setSelectedIconId(opt.id)}
                  className={cn(
                    "flex flex-col items-center justify-center gap-1.5 p-2 rounded-xl border transition-all duration-300 select-none active:scale-95 text-center cursor-pointer wizard-icon-btn",
                    isSelected 
                      ? cn("ring-2 shadow-sm border scale-[1.01] bg-primary/5", opt.color) 
                      : "border-slate-200/80 dark:border-border/30 bg-accent/15 opacity-75 hover:opacity-100 text-slate-500 dark:text-slate-400"
                  )}
                >
                  <OptIcon size={20} className={isSelected ? "" : "text-slate-500"} />
                  <span className="text-[11px] font-black tracking-tight text-slate-900 dark:text-slate-100">{opt.label}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Strategy cards - Bolder and larger for high contrast */}
        <div className="space-y-1.5">
          <label className="text-xs sm:text-[13px] font-extrabold uppercase tracking-wider text-slate-900 dark:text-slate-100 block">
            Select Default Strategy
          </label>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 wizard-strategy-grid">
            {strategies.map((strat) => {
              const Icon = strat.icon
              const isSelected = selectedStrategy === strat.id
              return (
                <button
                  key={strat.id}
                  type="button"
                  onClick={() => setSelectedStrategy(strat.id)}
                  className={cn(
                    "flex flex-col text-left p-4.5 rounded-xl border transition-all duration-300 relative overflow-hidden select-none active:scale-[0.98] group min-h-[145px] wizard-strategy-card",
                    isSelected
                      ? `ring-2 ${strat.ringColor} shadow-md scale-[1.01] ${strat.accent}`
                      : "border-slate-200/80 dark:border-border/50 bg-accent/25 opacity-75 hover:opacity-100 hover:border-primary/45 hover:bg-accent/40"
                  )}
                >
                  {/* Subtle card glow overlay */}
                  <div className={cn("absolute inset-0 bg-gradient-to-br opacity-0 transition-opacity duration-300 group-hover:opacity-100 pointer-events-none", strat.bgGlow)} />

                  {/* Tick badge on top-right */}
                  {isSelected && (
                    <span className="absolute top-4 right-4 flex h-5 w-5 items-center justify-center rounded-full bg-current">
                      <Check className="w-3 h-3 text-background font-black stroke-[3]" />
                    </span>
                  )}

                  <div className="flex items-center gap-2.5 mb-2.5 relative z-10">
                    <div className="p-2 rounded-lg bg-white/10 dark:bg-black/20 border border-white/20">
                      <Icon size={16} />
                    </div>
                    <div>
                      <h3 className="text-base font-black tracking-wide text-slate-900 dark:text-white leading-tight">{strat.label}</h3>
                      <p className="text-xs font-bold text-primary dark:text-cyan-400 leading-none mt-0.5">{strat.tagline}</p>
                    </div>
                  </div>

                  {/* Strategy Description */}
                  <p className="text-[11px] sm:text-xs text-slate-600 dark:text-slate-300 mt-1.5 relative z-10 leading-relaxed font-medium wizard-strategy-description">
                    {strat.description}
                  </p>
                </button>
              )
            })}
          </div>
        </div>

        {/* Start Button */}
        <div className="pt-2 flex justify-end wizard-start-container">
          <motion.button
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.97 }}
            onClick={handleStart}
            disabled={isSaving || !selectedStrategy || !workspaceName.trim()}
            className={cn(
              "px-8 py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-md select-none wizard-start-btn",
              (selectedStrategy && workspaceName.trim() && !isSaving)
                ? "bg-gradient-to-r from-blue-600 to-cyan-500 text-white shadow-primary/20 hover:shadow-primary/30"
                : "bg-muted text-muted-foreground/50 border border-border/50 cursor-not-allowed"
            )}
          >
            {isSaving ? 'Saving...' : 'Start Workspace'}
          </motion.button>
        </div>
      </motion.div>
    </div>
  )
}
