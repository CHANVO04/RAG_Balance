import { motion } from 'framer-motion'
import { useState } from 'react'
import { ExternalLink, FileText, Image as ImageIcon, Sigma, Table2 } from 'lucide-react'
import { SourceInfo, useStore } from '../../store'
import { useToastStore } from '../../store/toastStore'
import { cn } from '../../lib/utils'
import { isSameSource, sourceBadge, sourcePage, sourceRef, formatRelevance } from '../../lib/citationUtils'

interface Props {
  sourceId: number | string
  source?: SourceInfo
}

function sourceIcon(kind?: SourceInfo['kind']) {
  if (kind === 'image') return ImageIcon
  if (kind === 'formula') return Sigma
  if (kind === 'table') return Table2
  return FileText
}

function sourceKindLabel(source?: SourceInfo) {
  if (source?.kind === 'image') return 'Image source'
  if (source?.kind === 'formula') return 'Formula source'
  if (source?.kind === 'table') return 'Table source'
  return 'Text source'
}

function shortFileName(name?: string) {
  if (!name) return 'Missing file name'
  return name.length > 34 ? `${name.slice(0, 31)}...` : name
}

function badgeTone(kind?: SourceInfo['kind'], isActive = false, canOpen = true) {
  if (!canOpen) return 'border-border/40 bg-accent/40 text-muted-foreground/60 cursor-not-allowed'
  if (isActive) return 'border-transparent bg-gradient-to-r from-blue-600 to-cyan-500 text-white font-extrabold shadow-md shadow-primary/25'
  if (kind === 'table') return 'border-blue-500/20 bg-blue-500/8 text-blue-600 dark:text-blue-400 hover:bg-blue-500 hover:text-white dark:hover:text-white hover:border-transparent hover:shadow-sm hover:shadow-blue-500/20'
  if (kind === 'image') return 'border-purple-500/20 bg-purple-500/8 text-purple-600 dark:text-purple-400 hover:bg-purple-500 hover:text-white dark:hover:text-white hover:border-transparent hover:shadow-sm hover:shadow-purple-500/20'
  if (kind === 'formula') return 'border-amber-500/25 bg-amber-500/8 text-amber-600 dark:text-amber-400 hover:bg-amber-500 hover:text-white dark:hover:text-white hover:border-transparent hover:shadow-sm hover:shadow-amber-500/20'
  return 'border-cyan-500/25 bg-cyan-500/8 text-cyan-600 dark:text-cyan-400 hover:bg-cyan-500 hover:text-white dark:hover:text-white hover:border-transparent hover:shadow-sm hover:shadow-cyan-500/20'
}

export default function CitationBadge({ sourceId, source }: Props) {
  const { currentSource, activateSource } = useStore()
  const pushToast = useToastStore((s) => s.pushToast)
  const [isTooltipOpen, setTooltipOpen] = useState(false)
  
  let rawLabel = sourceRef(source, sourceId) || (typeof sourceId === 'number' ? sourceBadge(sourceId) : String(sourceId))
  // Format standard scientific prefix instead of ugly brackets
  let label = rawLabel
  if (source) {
    if (source.kind === 'table') label = `Table ${rawLabel}`
    else if (source.kind === 'formula') label = `Eq. ${rawLabel}`
    else if (source.kind === 'image') label = `Fig. ${rawLabel}`
    else label = `Ref ${rawLabel}`
  }

  const page = sourcePage(source)
  const canOpen = Boolean(source?.file_name)
  const isActive = isSameSource(currentSource, source)
  const Icon = sourceIcon(source?.kind)
  const showTooltip = isTooltipOpen && !isActive

  const handleClick = () => {
    if (!source) {
      pushToast({ type: 'error', title: 'Source unavailable', description: `${label} is not available in the current answer.` })
      return
    }
    if (!canOpen) {
      pushToast({ type: 'error', title: 'PDF source missing', description: `${label} does not include a file name.` })
      return
    }
    setTooltipOpen(false)
    activateSource(source)
  }

  if (!source) {
    return (
      <span
        className="relative inline-block mx-0.5"
        onMouseEnter={() => setTooltipOpen(true)}
        onMouseLeave={() => setTooltipOpen(false)}
        onFocus={() => setTooltipOpen(true)}
        onBlur={() => setTooltipOpen(false)}
      >
        <span className="rounded-full border border-border/70 bg-accent/40 px-2 py-0.5 align-middle font-mono text-[9px] font-bold text-muted-foreground select-all">
          {label}
        </span>
        <div 
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-52 -translate-x-1/2 rounded-xl border border-border bg-card p-3 text-xs shadow-2xl transition-all duration-150 select-none",
            showTooltip ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
          )}
        >
          Source metadata is unavailable.
        </div>
      </span>
    )
  }

  return (
    <span
      className="relative inline-block mx-0.5"
      onMouseEnter={() => setTooltipOpen(true)}
      onMouseLeave={() => setTooltipOpen(false)}
      onFocus={() => setTooltipOpen(true)}
      onBlur={() => setTooltipOpen(false)}
    >
      <motion.button
        whileHover={{ y: -1, scale: 1.04 }}
        whileTap={{ scale: 0.94 }}
        onClick={handleClick}
        disabled={!canOpen}
        className={cn(
          "inline-flex h-[21px] items-center gap-1.5 rounded-full border px-2.5 align-baseline font-sans text-[10px] font-bold leading-none transition-all mx-0.5 select-all hover:shadow-sm cursor-pointer",
          "focus:outline-none focus:ring-2 focus:ring-primary/30 focus:ring-offset-1 focus:ring-offset-background",
          badgeTone(source.kind, isActive, canOpen)
        )}
      >
        {isActive && <span className="w-1.5 h-1.5 rounded-full bg-cyan-300 animate-pulse-cyan shrink-0" />}
        <Icon size={10} strokeWidth={2.5} className="shrink-0" />
        <span>{label}</span>
      </motion.button>

      <div 
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-48 -translate-x-1/2 rounded-lg border border-border bg-card p-2 text-card-foreground shadow-xl transition-all duration-150 select-none",
          showTooltip ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
        )}
      >
        <div className="flex flex-col gap-1.5 select-none">
          <div className="flex items-start gap-2">
            <div className={cn("rounded-md p-1.5", isActive ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary")}>
              <Icon size={13} />
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-[10px] font-bold text-muted-foreground uppercase truncate">{`${sourceKindLabel(source)} ${label}`}</span>
              <span className="text-xs font-semibold truncate">{shortFileName(source.file_name)}</span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-1.5 mt-1">
            <div className="rounded-md bg-accent/50 p-2">
              <div className="text-[9px] text-muted-foreground uppercase">Page</div>
              <div className="text-xs font-bold">{page}</div>
            </div>
            <div className="rounded-md bg-accent/50 p-2">
              <div className="text-[9px] text-muted-foreground uppercase">Relevance</div>
              <div className="text-xs font-bold text-green-500">{formatRelevance(source.score)}%</div>
            </div>
          </div>

          {source.section_label && (
            <div className="rounded-md bg-accent/50 p-2">
              <div className="text-[9px] text-muted-foreground uppercase">Section</div>
              <div className="text-xs font-semibold truncate">{source.section_label}</div>
            </div>
          )}

          <div className={cn("mt-1 flex items-center gap-1 text-[9px] font-bold", canOpen ? "text-primary" : "text-muted-foreground")}>
            <ExternalLink size={10} />
            {canOpen ? 'CLICK TO HIGHLIGHT SOURCE' : 'SOURCE UNAVAILABLE'}
          </div>
        </div>

        <div className="absolute top-full left-1/2 -translate-x-1/2 border-[6px] border-transparent border-t-card" />
      </div>
    </span>
  )
}
