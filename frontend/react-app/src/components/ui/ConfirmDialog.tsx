import React from 'react'
import { AlertTriangle, X } from 'lucide-react'
import { cn } from '../../lib/utils'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  cancelLabel?: string
  typedValue?: string
  requiredText?: string
  isBusy?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Delete',
  cancelLabel = 'Cancel',
  typedValue = '',
  requiredText,
  isBusy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [inputValue, setInputValue] = React.useState('')

  React.useEffect(() => {
    if (open) setInputValue('')
  }, [open])

  React.useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !isBusy) onCancel()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isBusy, onCancel, open])

  if (!open) return null

  const required = requiredText ?? typedValue
  const requiresTyping = Boolean(required)
  const canConfirm = !isBusy && (!requiresTyping || inputValue === required)

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
              <AlertTriangle size={20} />
            </div>
            <div>
              <h2 className="text-base font-black tracking-tight text-foreground">{title}</h2>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{description}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={isBusy}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
            aria-label="Close confirmation"
          >
            <X size={16} />
          </button>
        </div>

        {requiresTyping && (
          <label className="mt-4 block">
            <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
              Type {required} to confirm
            </span>
            <input
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              disabled={isBusy}
              className="mt-2 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm font-semibold text-foreground outline-none transition-colors focus:border-destructive/60"
              autoFocus
            />
          </label>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isBusy}
            className="rounded-xl border border-border px-4 py-2 text-sm font-bold text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!canConfirm}
            className={cn(
              "rounded-xl bg-destructive px-4 py-2 text-sm font-black text-destructive-foreground shadow-lg shadow-destructive/15 transition-all",
              canConfirm ? "hover:-translate-y-0.5 hover:bg-destructive/90" : "cursor-not-allowed opacity-45",
            )}
          >
            {isBusy ? 'Deleting...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
