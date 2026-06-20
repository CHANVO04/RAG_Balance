import React, { useEffect, useRef, useState } from 'react'
import { ChevronDown, Search } from 'lucide-react'
import { cn } from '../../lib/utils'
import { motion, AnimatePresence } from 'framer-motion'

export default function ThinkingPanel({ thought, isStreaming }: { thought?: string, isStreaming?: boolean }) {
  const [isExpanded, setIsExpanded] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (isStreaming) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
    }
  }, [thought, isStreaming])

  useEffect(() => {
    if (!isStreaming && thought) setIsExpanded(false)
  }, [isStreaming, thought])

  if (!thought && !isStreaming) return null

  return (
    <div className="mb-4 rounded-2xl border border-border/60 bg-background/70 p-3">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between gap-3 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
      >
        <span className="flex items-center gap-2">
          <Search size={14} className={cn(isStreaming && "animate-pulse text-primary")} />
          <span>Research Trace</span>
          {isStreaming && <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />}
        </span>
        <ChevronDown size={15} className={cn("transition-transform duration-200", isExpanded && "rotate-180")} />
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden pt-3"
          >
            <div ref={scrollRef} className="p-4 rounded-xl bg-accent/20 border border-border/30 text-xs leading-relaxed text-muted-foreground font-mono max-h-32 overflow-y-auto whitespace-pre-wrap">
              {thought || "Preparing research trace..."}
              {isStreaming && <span className="inline-block w-1.5 h-3.5 ml-1 bg-primary/40 animate-pulse align-middle" />}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
