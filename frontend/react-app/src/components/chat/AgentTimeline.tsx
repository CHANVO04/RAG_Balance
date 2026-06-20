import React, { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, Circle, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import { AgentStep } from '../../store'

function elapsed(step: AgentStep) {
  if (step.status === 'running' && step.startedAt) {
    return `${Math.max(0.1, (performance.now() - step.startedAt) / 1000).toFixed(1)}s`
  }
  if (step.duration) return `${step.duration.toFixed(1)}s`
  return 'Waiting'
}

function StepIcon({ status }: { status: AgentStep['status'] }) {
  if (status === 'completed') return <CheckCircle2 size={16} />
  if (status === 'running') return <Loader2 size={16} className="animate-spin" />
  if (status === 'error') return <AlertCircle size={16} />
  return <Circle size={16} />
}

export default function AgentTimeline({ steps }: { steps: AgentStep[] }) {
  const [, setTick] = useState(0)

  useEffect(() => {
    if (!steps.some((s) => s.status === 'running')) return
    const id = window.setInterval(() => setTick((n) => n + 1), 500)
    return () => window.clearInterval(id)
  }, [steps])

  if (!steps || steps.length === 0) return null

  return (
    <div className="my-4 rounded-2xl border border-border/60 bg-background/70 p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div className="text-[10px] font-bold uppercase tracking-[0.24em] text-muted-foreground">
          Agent Execution
        </div>
        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
          <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
          Live
        </div>
      </div>

      <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-start gap-3">
        {steps.map((step, idx) => (
          <React.Fragment key={step.id}>
            <div className="flex min-w-0 flex-col items-center gap-2 text-center">
              <div
                className={cn(
                  'flex h-9 w-9 items-center justify-center rounded-full border-2 transition-all',
                  step.status === 'completed' && 'border-cyan-500 bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 shadow-md shadow-cyan-500/10',
                  step.status === 'running' && 'border-primary bg-primary/10 text-primary shadow-lg shadow-primary/20 animate-pulse',
                  step.status === 'error' && 'border-destructive bg-destructive/10 text-destructive',
                  step.status === 'pending' && 'border-border bg-card text-muted-foreground',
                )}
              >
                <StepIcon status={step.status} />
              </div>
              <div className="space-y-0.5">
                <div
                  className={cn(
                    'text-xs font-bold',
                    step.status === 'running' ? 'text-foreground' : 'text-muted-foreground',
                    step.status === 'completed' && 'text-cyan-600 dark:text-cyan-400',
                    step.status === 'error' && 'text-destructive',
                  )}
                >
                  {step.label}
                </div>
                <div className="text-[10px] font-medium text-muted-foreground/70">{elapsed(step)}</div>
              </div>
            </div>
            {idx < steps.length - 1 && (
              <div className="mt-4 h-0.5 w-12 rounded-full bg-border">
                <div
                  className={cn(
                    'h-full rounded-full transition-all duration-500',
                    steps[idx].status === 'completed' ? 'w-full bg-cyan-500 shadow-sm shadow-cyan-500/50' : 'w-1/3 bg-primary/40',
                    steps[idx + 1].status === 'pending' && steps[idx].status !== 'completed' && 'w-0',
                  )}
                />
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}
