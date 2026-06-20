import React, { useState, useRef, useEffect } from 'react'
import { Send, Square, Command } from 'lucide-react'
import { cn } from '../../lib/utils'
import { motion } from 'framer-motion'

interface Props {
  onSend: (text: string) => void
  onAbort: () => void
  disabled?: boolean
  isStreaming?: boolean
  statusMsg?: string
}

export default function ChatInput({ onSend, onAbort, disabled, isStreaming, statusMsg }: Props) {
  const [text, setText] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    if (text.trim() && !isStreaming) {
      onSend(text.trim())
      setText('')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    } else if (e.key === 'Escape' && isStreaming) {
      e.preventDefault()
      onAbort()
    }
  }

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 200)}px`
    }
  }, [text])

  return (
    <div className="relative space-y-2">
      {/* Status Bar */}
      {statusMsg && (
        <div className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/5 border border-primary/20 w-fit mx-auto mb-2 animate-in fade-in slide-in-from-bottom-2">
          <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          <span className="text-[10px] font-bold text-primary uppercase tracking-wider">{statusMsg}</span>
        </div>
      )}

      {/* Input Container */}
      <div className={cn(
        "relative flex flex-col p-2 rounded-3xl glass shadow-premium transition-all duration-300",
        isStreaming ? "ring-2 ring-primary/25 border-primary/35" : "focus-within:ring-2 focus-within:ring-primary/25 focus-within:border-primary/35"
      )}>
        <textarea
          ref={inputRef}
          data-chat-input="true"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your documents... (Enter to send)"
          rows={1}
          className="w-full bg-transparent px-4 py-3 text-sm resize-none focus:outline-none placeholder:text-muted-foreground/50"
          disabled={disabled}
        />

        <div className="flex items-center justify-between px-4 pb-2">
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground font-medium">
            <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-accent border border-border">
              <Command size={10} />
              <span>Enter to send</span>
            </div>
            <span>Shift + Enter for newline</span>
          </div>

          <motion.button
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.94 }}
            onClick={isStreaming ? onAbort : handleSend}
            disabled={(!text.trim() && !isStreaming) || disabled}
            className={cn(
              "p-2.5 rounded-2xl transition-all active:scale-95 shadow-lg",
              isStreaming 
                ? "bg-destructive text-destructive-foreground shadow-destructive/20" 
                : "bg-primary text-primary-foreground shadow-primary/20 hover:shadow-primary/30 disabled:opacity-50 disabled:shadow-none"
            )}
          >
            {isStreaming ? <Square size={18} fill="currentColor" /> : <Send size={18} />}
          </motion.button>
        </div>
      </div>
    </div>
  )
}
