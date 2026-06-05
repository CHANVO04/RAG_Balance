import React from 'react'
import { Filter, X, Check } from 'lucide-react'
import { cn } from '../../lib/utils'

interface GraphFilterProps {
  availableTypes: string[]
  selectedTypes: Set<string>
  onToggleType: (type: string) => void
  onSelectAll: () => void
  onClearAll: () => void
  onClose?: () => void
}

const TYPE_STYLES: Record<string, { bg: string; border: string; text: string }> = {
  Person: {
    bg: 'bg-blue-50/80 dark:bg-blue-950/30',
    border: 'border-blue-200 dark:border-blue-900/60',
    text: 'text-blue-700 dark:text-blue-300',
  },
  Method: {
    bg: 'bg-emerald-50/80 dark:bg-emerald-950/30',
    border: 'border-emerald-200 dark:border-emerald-900/60',
    text: 'text-emerald-700 dark:text-emerald-300',
  },
  Dataset: {
    bg: 'bg-amber-50/80 dark:bg-amber-950/30',
    border: 'border-amber-200 dark:border-amber-900/60',
    text: 'text-amber-700 dark:text-amber-300',
  },
  Model: {
    bg: 'bg-purple-50/80 dark:bg-purple-950/30',
    border: 'border-purple-200 dark:border-purple-900/60',
    text: 'text-purple-700 dark:text-purple-300',
  },
  Formula: {
    bg: 'bg-pink-50/80 dark:bg-pink-950/30',
    border: 'border-pink-200 dark:border-pink-900/60',
    text: 'text-pink-700 dark:text-pink-300',
  },
  Image: {
    bg: 'bg-orange-50/80 dark:bg-orange-950/30',
    border: 'border-orange-200 dark:border-orange-900/60',
    text: 'text-orange-700 dark:text-orange-300',
  },
  Document: {
    bg: 'bg-sky-50/80 dark:bg-sky-950/30',
    border: 'border-sky-200 dark:border-sky-900/60',
    text: 'text-sky-700 dark:text-sky-300',
  },
  Concept: {
    bg: 'bg-slate-50/80 dark:bg-slate-900/30',
    border: 'border-slate-200 dark:border-slate-800',
    text: 'text-slate-700 dark:text-slate-300',
  },
}

export default function GraphFilter({
  availableTypes,
  selectedTypes,
  onToggleType,
  onSelectAll,
  onClearAll,
  onClose,
}: GraphFilterProps) {
  // ESC key listener for closing
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && onClose) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const allSelected = availableTypes.length > 0 && availableTypes.every((t) => selectedTypes.has(t))
  const noneSelected = selectedTypes.size === 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/60 backdrop-blur-md transition-all duration-300">
      {/* Click outside to close */}
      <div 
        className="absolute inset-0 bg-transparent cursor-default" 
        onClick={onClose}
      />
      
      {/* Centered Card */}
      <div className="relative w-full max-w-sm overflow-hidden rounded-2xl border border-border/70 bg-card/90 shadow-2xl backdrop-blur-md transition-all duration-300 transform scale-100 p-5 flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/40 pb-3 mb-4 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8.5 w-8.5 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              <Filter size={16} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-foreground">Bộ lọc thực thể</h3>
              <p className="text-[11px] text-muted-foreground mt-0.5">Lọc hiển thị theo loại đối tượng</p>
            </div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-all duration-200 active:scale-95"
              aria-label="Đóng bộ lọc"
            >
              <X size={16} />
            </button>
          )}
        </div>

        {/* Sub-header controls (Select All / Clear All) */}
        <div className="flex items-center justify-between text-[11px] px-1 mb-3 shrink-0">
          <span className="font-bold text-muted-foreground uppercase tracking-wider">
            Loại thực thể ({selectedTypes.size}/{availableTypes.length})
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={onSelectAll}
              disabled={allSelected}
              className="font-bold text-emerald-600 dark:text-emerald-400 hover:opacity-85 disabled:opacity-40 disabled:pointer-events-none transition-opacity"
            >
              Chọn tất cả
            </button>
            <span className="text-border/60">|</span>
            <button
              onClick={onClearAll}
              disabled={noneSelected}
              className="font-bold text-muted-foreground hover:text-foreground disabled:opacity-40 disabled:pointer-events-none transition-colors"
            >
              Bỏ chọn
            </button>
          </div>
        </div>

        {/* Custom Checklist Container */}
        <div className="overflow-y-auto pr-1 space-y-1.5 flex-1 scrollbar-thin">
          {availableTypes.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              Không tìm thấy loại thực thể nào trong hệ thống.
            </div>
          ) : (
            availableTypes.map((type) => {
              const isChecked = selectedTypes.has(type)
              const styles = TYPE_STYLES[type] || TYPE_STYLES.Concept

              return (
                <div
                  key={type}
                  onClick={() => onToggleType(type)}
                  className={cn(
                    "flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer transition-all border text-xs select-none",
                    isChecked 
                      ? "bg-accent/40 border-border/80 shadow-sm" 
                      : "border-transparent hover:bg-accent/30 bg-transparent"
                  )}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    {/* Custom Checkbox Box */}
                    <div className={cn(
                      "flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-md border transition-all",
                      isChecked 
                        ? "bg-emerald-500 border-emerald-500 text-white shadow-sm shadow-emerald-500/10" 
                        : "border-muted-foreground/30 bg-background hover:border-muted-foreground/50"
                    )}>
                      {isChecked && <Check size={11} strokeWidth={3} className="animate-in fade-in zoom-in-75 duration-150" />}
                    </div>
                    
                    {/* Entity Label */}
                    <span className="font-semibold text-foreground truncate">{type}</span>
                  </div>

                  {/* Colored indicator tag/pill */}
                  <span 
                    className={cn(
                      "px-2 py-0.5 rounded-full text-[10px] font-bold border transition-colors",
                      styles.bg,
                      styles.border,
                      styles.text
                    )}
                  >
                    {type}
                  </span>
                </div>
              )
            })
          )}
        </div>

        {/* Footer actions */}
        {onClose && (
          <div className="mt-4 pt-3.5 border-t border-border/40 flex justify-end shrink-0">
            <button
              onClick={onClose}
              className="rounded-xl bg-foreground text-background font-bold text-xs px-4 py-2 hover:opacity-90 transition-all active:scale-[0.98] shadow-md shadow-foreground/5"
            >
              Hoàn tất
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
