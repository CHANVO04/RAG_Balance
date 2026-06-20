import { useEffect, useRef, useState } from 'react'
import { useStore } from '../../store'
import { useChat } from '../../hooks/useChat'
import ChatMessage from '../chat/ChatMessage'
import ChatInput from '../chat/ChatInput'
import { Search, Sparkles } from 'lucide-react'
import { motion } from 'framer-motion'

export default function CenterPanel() {
  const messages = useStore((s) => s.messages)
  const endRef   = useRef<HTMLDivElement>(null)
  const { sendMessage, isStreaming, statusMsg, abort } = useChat()

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const onEscape = () => {
      if (isStreaming) abort()
    }
    document.addEventListener('rag:escape', onEscape)
    return () => {
      document.removeEventListener('rag:escape', onEscape)
    }
  }, [abort, isStreaming])

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-background relative">
      {/* Header */}
      <header className="h-16 flex items-center justify-between px-6 border-b border-border/50 bg-background/80 backdrop-blur-md z-10">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-primary/10 text-primary">
            <Sparkles size={18} />
          </div>
          <div>
            <h2 className="text-sm font-bold">Research Assistant</h2>
            <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-bold">GPT-4.1-mini • Decoupled Mode</p>
          </div>
        </div>
        
      </header>

      {/* Main Chat Area */}
      <div className="flex-1 overflow-y-auto px-6 py-8 relative">
        <div className="mx-auto w-full max-w-none">
          {messages.length === 0 && !isStreaming && (
            <motion.div 
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="h-[60vh] flex flex-col items-center justify-center text-center space-y-6"
            >
              <div className="w-20 h-20 rounded-3xl bg-primary/10 flex items-center justify-center text-primary shadow-2xl shadow-primary/20 rotate-12">
                <Search size={40} />
              </div>
              <div className="space-y-2">
                <h1 className="text-3xl font-bold tracking-tight">Scientific <span className="text-primary">RAG</span></h1>
                <p className="text-muted-foreground max-w-sm mx-auto text-sm">
                  Upload your documents and explore them with an AI research assistant.
                  Press <kbd className="px-1.5 py-0.5 rounded border border-border bg-accent text-[10px] font-mono">/</kbd> to focus the input.
                </p>
              </div>
            </motion.div>
          )}
          
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}

          <div ref={endRef} className="h-12" />
        </div>
      </div>

      {/* Input Area */}
      <div className="p-6 bg-gradient-to-t from-background via-background to-transparent">
        <div className="mx-auto w-full max-w-none">
          <ChatInput
            onSend={sendMessage}
            onAbort={abort}
            disabled={false}
            isStreaming={isStreaming}
            statusMsg={statusMsg}
          />
        </div>
      </div>
    </div>
  )
}
