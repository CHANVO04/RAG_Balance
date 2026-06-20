import React, { useMemo } from 'react'
import { InlineMath, BlockMath } from 'react-katex'
import { KGEvidenceInfo, Message, Segment, SourceInfo } from '../../store'
import { cn } from '../../lib/utils'
import CitationBadge from './CitationBadge'
import GraphCitationBadge from './GraphCitationBadge'
import ThinkingPanel from './ThinkingPanel'
import AgentTimeline from './AgentTimeline'
import CodeBlock from './CodeBlock'
import { motion } from 'framer-motion'
import { Skeleton } from '../ui/Skeleton'
import { Image as ImageIcon, Sigma, Table2, TextQuote } from 'lucide-react'
import { mergeAdjacentTextSegments } from '../../lib/messageSegments'

function renderMarkdownText(text: string, keyPrefix: string, isUser: boolean = false) {
  const lines = text.split('\n');
  const renderedElements: React.ReactNode[] = [];

  const parseInlineMarkdown = (lineText: string, baseKey: string) => {
    const parts = lineText.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
    return parts.map((part, idx) => {
      const key = `${baseKey}-${idx}`;
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={key} className={cn("font-semibold", isUser ? "text-white" : "text-foreground")}>{part.slice(2, -2)}</strong>;
      }
      return <span key={key} className={isUser ? "text-primary-foreground" : ""}>{part}</span>;
    });
  };

  let currentList: React.ReactNode[] = [];
  let currentListType: 'bullet' | 'number' | null = null;

  const flushList = (key: string) => {
    if (currentList.length === 0) return null;
    const listKey = `${key}-list-wrapper`;
    const items = [...currentList];
    currentList = [];
    const type = currentListType;
    currentListType = null;

    if (type === 'bullet') {
      return (
        <ul key={listKey} className={cn("list-disc ml-5 mb-3 space-y-1.5 leading-relaxed select-text", isUser ? "text-primary-foreground" : "text-card-foreground/90")}>
          {items}
        </ul>
      );
    } else {
      return (
        <ol key={listKey} className={cn("list-decimal ml-5 mb-3 space-y-1.5 leading-relaxed select-text", isUser ? "text-primary-foreground" : "text-card-foreground/90")}>
          {items}
        </ol>
      );
    }
  };

  lines.forEach((line, index) => {
    const key = `${keyPrefix}-line-${index}`;
    const bulletMatch = line.match(/^\s*[-*]\s+(.*)$/);
    const numberMatch = line.match(/^\s*(\d+)\.\s+(.*)$/);

    if (bulletMatch) {
      const content = bulletMatch[1];
      if (currentListType && currentListType !== 'bullet') {
        const listNode = flushList(key);
        if (listNode) renderedElements.push(listNode);
      }
      currentListType = 'bullet';
      currentList.push(
        <li key={`${key}-item`} className={cn("pl-1 text-sm font-normal", isUser ? "text-primary-foreground" : "")}>
          {parseInlineMarkdown(content, `list-bullet-${index}`)}
        </li>
      );
    } else if (numberMatch) {
      const content = numberMatch[2];
      if (currentListType && currentListType !== 'number') {
        const listNode = flushList(key);
        if (listNode) renderedElements.push(listNode);
      }
      currentListType = 'number';
      currentList.push(
        <li key={`${key}-item`} className={cn("pl-1 text-sm font-normal", isUser ? "text-primary-foreground" : "")}>
          {parseInlineMarkdown(content, `list-number-${index}`)}
        </li>
      );
    } else {
      // Normal paragraph line
      const listNode = flushList(key);
      if (listNode) renderedElements.push(listNode);

      if (line.trim() === '') {
        renderedElements.push(<div key={key} className="h-2" />);
      } else {
        renderedElements.push(
          <p key={key} className={cn("mb-2.5 last:mb-0 leading-relaxed text-sm select-text", isUser ? "text-primary-foreground" : "text-card-foreground/95")}>
            {parseInlineMarkdown(line, `para-${index}`)}
          </p>
        );
      }
    }
  });

  const finalListNode = flushList(`${keyPrefix}-final`);
  if (finalListNode) renderedElements.push(finalListNode);

  return <div className="space-y-1">{renderedElements}</div>;
}

// Memoized Paragraph to avoid re-rendering old chunks during streaming
const MemoizedParagraph = React.memo(({
  segments,
  sourceMap,
  kgSourceMap,
  isUser = false,
}: {
  segments: Segment[]
  sourceMap: Map<string, SourceInfo>
  kgSourceMap: Map<string, KGEvidenceInfo>
  isUser?: boolean
}) => {
  return (
    <div className="mb-4 last:mb-0">
      {segments.map((seg, i) => {
        if (seg.type === 'text') return <React.Fragment key={i}>{renderMarkdownText(seg.content, `text-${i}`, isUser)}</React.Fragment>
        if (seg.type === 'latex_inline') return <InlineMath key={i} math={seg.content} />
        if (seg.type === 'latex_block') return <BlockMath key={i} math={seg.content} />
        if (seg.type === 'cite') {
          const sourceId = seg.content
          return <CitationBadge key={i} sourceId={sourceId} source={sourceMap.get(sourceId)} />
        }
        if (seg.type === 'kg_cite') {
          const evidenceId = seg.content
          return <GraphCitationBadge key={i} evidenceId={evidenceId} evidence={kgSourceMap.get(evidenceId)} />
        }
        return null
      })}
    </div>
  )
})

export default function ChatMessage({ message, isStreaming }: { message: Message; isStreaming?: boolean }) {
  const isUser = message.role === 'user'
  const streaming = isStreaming ?? message.isStreaming
  const thinkingActive = streaming && !message.thinkingComplete
  const [showFinalThought, setShowFinalThought] = React.useState(false)
  const sourceMap = useMemo(() => {
    const entries: [string, SourceInfo][] = []
    message.sources.forEach((source) => {
      entries.push([String(source.id), source])
      if (source.citation_id) entries.push([source.citation_id, source])
      if (source.ref_id) entries.push([source.ref_id, source])
    })
    return new Map(entries)
  }, [message.sources])
  const kgSourceMap = useMemo(() => {
    const entries: [string, KGEvidenceInfo][] = []
    message.kgSources?.forEach((source) => {
      entries.push([source.id, source])
    })
    return new Map(entries)
  }, [message.kgSources])
  const sourceSummary = useMemo(() => {
    const refs = new Set<string>()
    let imageCount = 0
    let tableCount = 0
    let formulaCount = 0
    let textCount = 0
    message.sources.forEach((source) => {
      const ref = source.ref_id || source.citation_id || String(source.id)
      if (refs.has(ref)) return
      refs.add(ref)
      if (source.kind === 'image') imageCount += 1
      else if (source.kind === 'table') tableCount += 1
      else if (source.kind === 'formula') formulaCount += 1
      else textCount += 1
    })
    return { total: refs.size, imageCount, tableCount, formulaCount, textCount }
  }, [message.sources])
  
  // Group segments into paragraphs for memoization
  const paragraphs = useMemo(() => {
    const p: Segment[][] = [[]]
    mergeAdjacentTextSegments(message.segments).forEach((seg: Segment) => {
      if (seg.type === 'text' && seg.content.includes('\n\n')) {
        const parts = seg.content.split('\n\n')
        parts.forEach((part: string, i: number) => {
          if (i > 0) p.push([])
          p[p.length - 1].push({ ...seg, content: part })
        })
      } else {
        p[p.length - 1].push(seg)
      }
    })
    return p
  }, [message.segments])

  return (
    <motion.div
      initial={{ opacity: 0, y: 14, x: isUser ? 10 : -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
      className={cn(
        "flex w-full mb-8",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      <div className={cn(
        "group",
        isUser ? "flex max-w-[85%] flex-col items-end" : "flex w-full max-w-[96%] flex-col items-start"
      )}>
        {/* Role Badge */}
        {!isUser && (
          <div className="flex items-center gap-2 mb-2 ml-1">
            <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center text-primary border border-primary/20">
              <span className="text-[10px] font-bold">AI</span>
            </div>
            <span className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Scientific Agent</span>
          </div>
        )}

        {/* Content Bubble */}
        <motion.div
          whileHover={{ y: -1 }}
          transition={{ duration: 0.16, ease: 'easeOut' }}
          className={cn(
          "relative px-5 py-4 rounded-3xl text-sm leading-relaxed shadow-sm",
          isUser 
            ? "bg-primary text-primary-foreground rounded-tr-none" 
            : "bg-card border border-border/50 rounded-tl-none shadow-premium"
        )}>
          {/* Thinking & Steps - active when streaming */}
          {!isUser && streaming && (
            <div className="mb-4 space-y-4">
              <ThinkingPanel thought={message.thought} isStreaming={thinkingActive} />
              <AgentTimeline steps={message.steps || []} />
            </div>
          )}
          {/* Thinking & Steps - collapsible after finished */}
          {!isUser && !streaming && message.thought && (
            <div className="mb-4 border-b border-border/30 pb-2">
              <button
                onClick={() => setShowFinalThought(!showFinalThought)}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground font-medium transition-colors"
              >
                <span className="text-[14px]">🧠</span>
                <span>{showFinalThought ? 'Hide thought process' : 'View thought process'}</span>
              </button>
              {showFinalThought && (
                <div className="mt-3 space-y-4">
                  <ThinkingPanel thought={message.thought} isStreaming={false} />
                  <AgentTimeline steps={message.steps || []} />
                </div>
              )}
            </div>
          )}

          {/* Text Content */}
          <div className="prose prose-sm max-w-none dark:prose-invert">
            {!isUser && streaming && message.segments.length === 0 && (
              <div className="space-y-2 py-1">
                <Skeleton variant="shimmer" className="h-3 w-64" />
                <Skeleton variant="shimmer" className="h-3 w-52" />
              </div>
            )}
            {paragraphs.map((p, i) => (
              <MemoizedParagraph key={i} segments={p} sourceMap={sourceMap} kgSourceMap={kgSourceMap} isUser={isUser} />
            ))}
            {streaming && (
              <span className="inline-block w-1.5 h-4 bg-primary/40 animate-pulse ml-1 align-middle" />
            )}
          </div>
        </motion.div>

        {/* Citations Footer */}
        {!isUser && message.sources.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2 rounded-full border border-border/70 bg-card/70 px-3 py-1.5 text-[11px] font-semibold text-muted-foreground shadow-sm">
            <span className="flex items-center gap-1 text-emerald-600">
              <TextQuote size={12} />
              {sourceSummary.total} sources
            </span>
            {sourceSummary.tableCount > 0 && (
              <span className="flex items-center gap-1">
                <Table2 size={12} />
                {sourceSummary.tableCount} tables
              </span>
            )}
            {sourceSummary.imageCount > 0 && (
              <span className="flex items-center gap-1">
                <ImageIcon size={12} />
                {sourceSummary.imageCount} images
              </span>
            )}
            {sourceSummary.formulaCount > 0 && (
              <span className="flex items-center gap-1">
                <Sigma size={12} />
                {sourceSummary.formulaCount} formulas
              </span>
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}
