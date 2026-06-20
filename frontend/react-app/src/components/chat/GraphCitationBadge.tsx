import { motion } from 'framer-motion'
import { Network } from 'lucide-react'
import { KGEvidenceInfo, useStore } from '../../store'
import { cn } from '../../lib/utils'

interface Props {
  evidenceId: string
  evidence?: KGEvidenceInfo
}

function badgeTitle(evidenceId: string, evidence?: KGEvidenceInfo) {
  if (!evidence) return `Graph evidence ${evidenceId} is unavailable in this answer.`
  return `${evidence.subject} ${evidence.relation} ${evidence.object}`
}

export default function GraphCitationBadge({ evidenceId, evidence }: Props) {
  const focusGraphEvidence = useStore((s) => s.focusGraphEvidence)
  const graphFocus = useStore((s) => s.graphFocus)
  const isActive = Boolean(evidence?.id && graphFocus?.evidenceId === evidence.id)
  const canFocus = Boolean(evidence)

  const handleClick = () => {
    if (!evidence) return
    focusGraphEvidence(evidence)
  }

  if (!canFocus) {
    return (
      <span
        title={badgeTitle(evidenceId)}
        className="inline-flex h-[21px] items-center gap-1.5 rounded-full border border-border/40 bg-accent/40 px-2.5 align-baseline font-sans text-[10px] font-bold leading-none text-muted-foreground/60 mx-0.5 cursor-not-allowed select-all"
      >
        <Network size={10} strokeWidth={2.5} className="shrink-0" />
        <span>{evidenceId}</span>
      </span>
    )
  }

  return (
    <motion.button
      type="button"
      whileHover={{ y: -1, scale: 1.04 }}
      whileTap={{ scale: 0.94 }}
      onClick={handleClick}
      title={badgeTitle(evidenceId, evidence)}
      aria-label={`Focus graph evidence ${evidenceId}: ${badgeTitle(evidenceId, evidence)}`}
      className={cn(
        "inline-flex h-[21px] items-center gap-1.5 rounded-full border px-2.5 align-baseline font-sans text-[10px] font-bold leading-none transition-all mx-0.5 select-all cursor-pointer",
        "focus:outline-none focus:ring-2 focus:ring-primary/30 focus:ring-offset-1 focus:ring-offset-background",
        isActive
          ? "border-transparent bg-gradient-to-r from-emerald-600 to-cyan-500 text-white font-extrabold shadow-md shadow-emerald-500/25"
          : "border-emerald-500/25 bg-emerald-500/8 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500 hover:text-white dark:hover:text-white hover:border-transparent hover:shadow-sm hover:shadow-emerald-500/20",
      )}
    >
      {isActive && <span className="w-1.5 h-1.5 rounded-full bg-cyan-200 animate-pulse-cyan shrink-0" />}
      <Network size={10} strokeWidth={2.5} className="shrink-0" />
      <span>{evidenceId}</span>
    </motion.button>
  )
}
