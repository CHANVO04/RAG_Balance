import React from 'react'
import { FileText, Layers, Hash, Clock, HardDrive, Trash2 } from 'lucide-react'
import { cn, formatBytes } from '../../lib/utils'
import { DocumentInfo } from '../../store'
import { motion } from 'framer-motion'

export default function DocumentChip({ doc, isProcessing, onDelete }: { doc: DocumentInfo; isProcessing?: boolean; onDelete?: () => void }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.995 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className={cn(
        "group relative bg-card border border-border/50 rounded-2xl p-4 shadow-sm hover:shadow-md transition-all",
        isProcessing && "animate-shimmer overflow-hidden"
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary shrink-0">
            <FileText size={20} />
          </div>
          <div className="min-w-0">
            <h4 className="text-sm font-semibold truncate group-hover:text-primary transition-colors">
              {doc.file_name}
            </h4>
            <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
              <span>{doc.file_size ? formatBytes(doc.file_size) : '--'}</span>
              <span>•</span>
              <span>{new Date(doc.ingested_at).toLocaleDateString()}</span>
            </div>
          </div>
        </div>
        <motion.button
          whileHover={{ scale: 1.08 }}
          whileTap={{ scale: 0.94 }}
          onClick={onDelete}
          className="p-1.5 rounded-lg hover:bg-destructive/10 hover:text-destructive opacity-0 group-hover:opacity-100 transition-all"
        >
          <Trash2 size={16} />
        </motion.button>
      </div>

      <div className="grid grid-cols-2 gap-2 mt-4">
        <div className="flex items-center gap-2 p-2 rounded-xl bg-accent/50 border border-border/20">
          <Layers size={14} className="text-muted-foreground" />
          <div className="flex flex-col">
            <span className="text-[9px] font-bold text-muted-foreground uppercase leading-none">Pages</span>
            <span className="text-xs font-bold leading-tight">{doc.total_pages}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 p-2 rounded-xl bg-accent/50 border border-border/20">
          <Hash size={14} className="text-muted-foreground" />
          <div className="flex flex-col">
            <span className="text-[9px] font-bold text-muted-foreground uppercase leading-none">Chunks</span>
            <span className="text-xs font-bold leading-tight">{doc.chunk_count}</span>
          </div>
        </div>
      </div>

      {isProcessing && (
        <div className="absolute inset-x-0 bottom-0 h-1 bg-primary/20">
          <motion.div 
            className="h-full bg-primary"
            initial={{ width: "0%" }}
            animate={{ width: "100%" }}
            transition={{ duration: 2, repeat: Infinity }}
          />
        </div>
      )}
    </motion.div>
  )
}
