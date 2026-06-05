import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { cn } from '../../lib/utils'

interface GraphCircleNodeData {
  label: string
  type?: string
  degree?: number
  isDimmed?: boolean
}

const TYPE_STYLES: Record<string, { gradient: string; border: string; text: string; glow: string }> = {
  Person: {
    gradient: 'from-blue-50 to-blue-200 dark:from-blue-950/40 dark:to-blue-900/60',
    border: 'border-blue-400 dark:border-blue-700',
    text: 'text-blue-900 dark:text-blue-100',
    glow: 'shadow-blue-500/20 dark:shadow-blue-500/10',
  },
  Method: {
    gradient: 'from-emerald-50 to-emerald-200 dark:from-emerald-950/40 dark:to-emerald-900/60',
    border: 'border-emerald-400 dark:border-emerald-700',
    text: 'text-emerald-900 dark:text-emerald-100',
    glow: 'shadow-emerald-500/20 dark:shadow-emerald-500/10',
  },
  Dataset: {
    gradient: 'from-amber-50 to-amber-200 dark:from-amber-950/40 dark:to-amber-900/60',
    border: 'border-amber-400 dark:border-amber-700',
    text: 'text-amber-900 dark:text-amber-100',
    glow: 'shadow-amber-500/20 dark:shadow-amber-500/10',
  },
  Model: {
    gradient: 'from-purple-50 to-purple-200 dark:from-purple-950/40 dark:to-purple-900/60',
    border: 'border-purple-400 dark:border-purple-700',
    text: 'text-purple-900 dark:text-purple-100',
    glow: 'shadow-purple-500/20 dark:shadow-purple-500/10',
  },
  Formula: {
    gradient: 'from-pink-50 to-pink-200 dark:from-pink-950/40 dark:to-pink-900/60',
    border: 'border-pink-400 dark:border-pink-700',
    text: 'text-pink-900 dark:text-pink-100',
    glow: 'shadow-pink-500/20 dark:shadow-pink-500/10',
  },
  Image: {
    gradient: 'from-orange-50 to-orange-200 dark:from-orange-950/40 dark:to-orange-900/60',
    border: 'border-orange-400 dark:border-orange-700',
    text: 'text-orange-900 dark:text-orange-100',
    glow: 'shadow-orange-500/20 dark:shadow-orange-500/10',
  },
  Document: {
    gradient: 'from-sky-50 to-sky-200 dark:from-sky-950/40 dark:to-sky-900/60',
    border: 'border-sky-400 dark:border-sky-700',
    text: 'text-sky-900 dark:text-sky-100',
    glow: 'shadow-sky-500/20 dark:shadow-sky-500/10',
  },
  Concept: {
    gradient: 'from-slate-50 to-slate-200 dark:from-slate-900 dark:to-slate-800',
    border: 'border-slate-400 dark:border-slate-700',
    text: 'text-slate-900 dark:text-slate-100',
    glow: 'shadow-slate-500/20 dark:shadow-slate-500/10',
  },
}

function GraphCircleNode({ id, data, selected }: NodeProps<GraphCircleNodeData>) {
  const type = data.type || 'Concept'
  const degree = data.degree || 0
  const isDimmed = data.isDimmed || false
  const label = data.label || id

  // Scale node radius dynamically based on connectivity degree:
  // Math.min(45, Math.max(20, 20 + degree * 2.5))
  const radius = Math.min(45, Math.max(20, 20 + degree * 2.5))
  const diameter = radius * 2

  const style = TYPE_STYLES[type] || TYPE_STYLES.Concept

  return (
    <div
      className={cn(
        'relative flex items-center justify-center rounded-full border bg-gradient-to-br shadow-md transition-all duration-300 ease-in-out cursor-pointer',
        style.gradient,
        style.border,
        style.text,
        style.glow,
        // Selected state: ring-2 ring-emerald-500 scale-105 shadow-emerald-500/50
        selected && 'ring-2 ring-emerald-500 scale-105 shadow-lg shadow-emerald-500/50 z-20 border-emerald-500',
        // Dimmed state: opacity-20 scale-90 saturate-50
        isDimmed && 'opacity-20 scale-90 saturate-50 pointer-events-none'
      )}
      style={{
        width: `${diameter}px`,
        height: `${diameter}px`,
      }}
    >
      {/* Invisible Handles for connection routing */}
      <Handle
        type="target"
        position={Position.Top}
        className="opacity-0 w-0 h-0 pointer-events-none"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="opacity-0 w-0 h-0 pointer-events-none"
      />

      {/* Label container inside the circle */}
      <div className="absolute inset-0 flex items-center justify-center p-2 text-center select-none overflow-hidden">
        <span
          className={cn(
            'font-bold leading-tight break-words line-clamp-3 hyphens-auto',
            radius < 25 ? 'text-[8px]' : radius < 35 ? 'text-[9px]' : 'text-[10px]'
          )}
        >
          {label}
        </span>
      </div>
    </div>
  )
}

export default memo(GraphCircleNode)
