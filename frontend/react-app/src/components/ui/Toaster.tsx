import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { cn } from '../../lib/utils'
import { ToastItem, useToastStore } from '../../store/toastStore'

const iconByType = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
}

function ToastCard({ toast }: { toast: ToastItem }) {
  const dismissToast = useToastStore((s) => s.dismissToast)
  const Icon = iconByType[toast.type]

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -12, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -10, scale: 0.96 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className={cn(
        'pointer-events-auto flex w-80 gap-3 rounded-2xl border bg-card p-4 text-card-foreground shadow-premium',
        toast.type === 'success' && 'border-green-500/30',
        toast.type === 'error' && 'border-destructive/35',
        toast.type === 'info' && 'border-primary/30',
      )}
    >
      <div
        className={cn(
          'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl',
          toast.type === 'success' && 'bg-green-500/10 text-green-600',
          toast.type === 'error' && 'bg-destructive/10 text-destructive',
          toast.type === 'info' && 'bg-primary/10 text-primary',
        )}
      >
        <Icon size={17} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold leading-5">{toast.title}</div>
        {toast.description && (
          <div className="mt-1 line-clamp-3 text-xs leading-5 text-muted-foreground">{toast.description}</div>
        )}
      </div>
      <button
        onClick={() => dismissToast(toast.id)}
        className="rounded-lg p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        aria-label="Dismiss notification"
      >
        <X size={14} />
      </button>
    </motion.div>
  )
}

export default function Toaster() {
  const toasts = useToastStore((s) => s.toasts)

  return (
    <div className="pointer-events-none fixed right-5 top-5 z-[200] flex flex-col gap-3">
      <AnimatePresence initial={false}>
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} />
        ))}
      </AnimatePresence>
    </div>
  )
}

