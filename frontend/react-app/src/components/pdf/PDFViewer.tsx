import { useEffect, useMemo, useRef } from 'react'
import { ExternalLink, FileText, Image, Sigma, Table2, TextQuote } from 'lucide-react'
import { SourceInfo, useStore } from '../../store'
import { EvidenceKind, isSameSource, sourceGuidance, sourcePage, sourceRef, formatRelevance } from '../../lib/citationUtils'
import { cn } from '../../lib/utils'

const EVIDENCE_ICONS: Record<EvidenceKind, typeof TextQuote> = {
  text: TextQuote,
  table: Table2,
  image: Image,
  formula: Sigma,
}

function pdfUrl(source: SourceInfo) {
  const page = sourcePage(source)
  const base = source.pdf_url || (source.file_name ? `/data/${encodeURIComponent(source.file_name)}` : '')
  return base ? `${base}#page=${page}` : ''
}

function cleanContent(source: SourceInfo) {
  const text = (source.content || '').trim()
  if (!text) return 'No source text is available for this citation.'
  return text.length > 760 ? `${text.slice(0, 760).trim()}...` : text
}

interface SourceContentRendererProps {
  content: string;
}

function SourceContentRenderer({ content }: SourceContentRendererProps) {
  const text = content.trim();
  if (!text) {
    return <span className="text-xs text-muted-foreground italic">No source content available.</span>;
  }

  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];

  let currentTableRows: string[][] = [];
  let currentTableKey = '';

  const flushTable = (key: string) => {
    if (currentTableRows.length === 0) return null;
    
    const rows = [...currentTableRows];
    currentTableRows = [];

    // Check if this looks like a markdown table (usually has a header and a separator line |---|)
    if (rows.length >= 2 && rows[1].every(cell => /^\s*:-*-*:?\s*$/.test(cell) || /^\s*-+\s*$/.test(cell))) {
      const headers = rows[0];
      const dataRows = rows.slice(2);
      
      return (
        <div key={`${key}-table-wrapper`} className="w-full overflow-x-auto border border-border/60 rounded-lg my-3 shadow-sm bg-card select-text">
          <table className="w-full border-collapse text-left text-[11px]">
            <thead>
              <tr className="bg-muted/70 border-b border-border/80">
                {headers.map((h, i) => (
                  <th key={i} className="px-3 py-2 font-bold text-foreground text-xs">{h.trim()}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dataRows.map((row, rIdx) => (
                <tr 
                  key={rIdx} 
                  className={cn(
                    "border-b border-border/40 hover:bg-muted/30 transition-colors",
                    rIdx % 2 === 1 ? "bg-muted/15" : "bg-card"
                  )}
                >
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} className="px-3 py-1.5 font-medium text-muted-foreground/90">{cell.trim()}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    } else {
      // Fallback: render table lines as paragraphs if it was malformed
      return (
        <div key={`${key}-table-fallback`} className="my-2 p-2 bg-muted/40 rounded border border-border font-mono text-[10px] whitespace-pre-wrap select-text">
          {rows.map(r => r.join(' | ')).join('\n')}
        </div>
      );
    }
  };

  lines.forEach((line, index) => {
    const key = `content-line-${index}`;
    const trimmed = line.trim();

    // Skip system metadata markers completely
    if (
      trimmed === 'VISUAL ENRICHMENT:' ||
      trimmed.startsWith('[TABLE') ||
      trimmed.startsWith('[IMAGE') ||
      trimmed.startsWith('[FORMULA') ||
      trimmed === 'Markdown:' ||
      trimmed === 'Summary:'
    ) {
      return;
    }

    // Check if it is a Caption line
    if (trimmed.startsWith('Caption:')) {
      const tableNode = flushTable(key);
      if (tableNode) elements.push(tableNode);

      const captionText = trimmed.replace(/^Caption:\s*/, '');
      elements.push(
        <div key={key} className="bg-primary/5 border border-primary/20 rounded-md p-2.5 text-xs text-primary font-semibold flex items-start gap-2 mb-3 shadow-sm select-text leading-relaxed">
          <span className="text-base select-none">📋</span>
          <span>{captionText}</span>
        </div>
      );
      return;
    }

    // Check if it is a Figure Caption (e.g. Fig. 5. or Hình 5.)
    if (/^(fig|figure|hình)\.?\s*\d+/i.test(trimmed)) {
      const tableNode = flushTable(key);
      if (tableNode) elements.push(tableNode);

      elements.push(
        <div key={key} className="bg-indigo-500/5 border border-indigo-500/20 rounded-md p-2.5 text-xs text-indigo-700 dark:text-indigo-300 font-semibold flex items-start gap-2 my-2.5 shadow-sm select-text leading-relaxed">
          <span className="text-base select-none">🖼️</span>
          <span>{trimmed}</span>
        </div>
      );
      return;
    }

    // Check if it is a table line (starts and ends with pipe '|' or contains multiple pipes)
    if (trimmed.startsWith('|') && trimmed.endsWith('|') && trimmed.length > 2) {
      // Split by pipe and filter out leading and trailing empty elements
      const cells = line.split('|').slice(1, -1);
      currentTableRows.push(cells);
      currentTableKey = currentTableKey || key;
    } else {
      // Normal paragraph line
      const tableNode = flushTable(currentTableKey || key);
      currentTableKey = '';
      if (tableNode) elements.push(tableNode);

      if (trimmed === '') {
        elements.push(<div key={key} className="h-1.5" />);
      } else {
        // If the paragraph has multiple definitions (contains '=' multiple times)
        const eqCount = (trimmed.match(/=/g) || []).length;
        if (eqCount >= 2) {
          // Split by periods followed by spaces
          const parts = trimmed.split(/\.\s+/g);
          const pills = parts.map((part, pIdx) => {
            const partTrimmed = part.trim();
            if (!partTrimmed) return null;
            
            const eqIndex = partTrimmed.indexOf('=');
            if (eqIndex !== -1) {
              const label = partTrimmed.slice(0, eqIndex).trim();
              const value = partTrimmed.slice(eqIndex + 1).trim();
              return (
                <div key={pIdx} className="bg-accent/60 border border-border/80 rounded-md px-2 py-1 text-[11px] font-medium inline-flex items-center gap-1.5 shadow-sm hover:border-primary/30 transition-colors">
                  <span className="text-muted-foreground">{label}</span>
                  <span className="text-foreground font-semibold select-all bg-background/60 px-1 rounded border border-border/40">{value}</span>
                </div>
              );
            }
            return (
              <span key={pIdx} className="text-xs text-card-foreground/90 font-normal self-center">
                {partTrimmed}
              </span>
            );
          }).filter(Boolean);

          elements.push(
            <div key={key} className="flex flex-wrap gap-2 my-3 p-3 bg-muted/20 border border-border/40 rounded-lg">
              {pills}
            </div>
          );
        } else {
          elements.push(
            <p key={key} className="mb-2 last:mb-0 text-xs text-card-foreground/90 leading-relaxed select-text font-normal">
              {line}
            </p>
          );
        }
      }
    }
  });

  const finalTableNode = flushTable(currentTableKey || 'final');
  if (finalTableNode) elements.push(finalTableNode);

  return <div className="space-y-1 py-1 select-text">{elements}</div>;
}

function SourceCard({ source, active }: { source: SourceInfo; active: boolean }) {
  const guidance = sourceGuidance(source)
  const Icon = EVIDENCE_ICONS[guidance.kind]
  const ref = sourceRef(source, source.id)
  const url = pdfUrl(source)

  const openOriginalPdf = () => {
    if (url) window.open(url, '_blank', 'noopener,noreferrer')
  }

  return (
    <article
      id={`source-${ref}`}
      data-source-ref={ref}
      className={cn(
        'rounded-lg border bg-card p-3 shadow-sm transition-all',
        active ? 'border-primary shadow-md shadow-primary/10 ring-2 ring-primary/20' : 'border-border/70'
      )}
    >
      <div className="flex items-start gap-3">
        <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-md', active ? 'bg-primary text-primary-foreground' : 'bg-primary/10 text-primary')}>
          <Icon size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-primary/10 px-2 py-0.5 font-mono text-[10px] font-bold text-primary">[{ref}]</span>
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{guidance.label}</span>
            <span className="text-[10px] text-muted-foreground">P{sourcePage(source)}</span>
            <span className="text-[10px] font-semibold text-green-600">{formatRelevance(source.score)}%</span>
          </div>
          <h3 className="mt-1 truncate text-sm font-semibold text-foreground" title={source.file_name}>
            {source.file_name || 'Unknown source'}
          </h3>
          {source.section_label && (
            <p className="mt-1 truncate text-xs text-muted-foreground">{source.section_label}</p>
          )}
        </div>
        <button
          onClick={openOriginalPdf}
          disabled={!url}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-40"
          title="Open original PDF in a new browser tab"
        >
          <ExternalLink size={14} />
        </button>
      </div>

      {source.asset_url && source.kind === 'image' && (
        <figure className="mt-4 overflow-hidden rounded-md border border-border bg-muted/30">
          <img src={source.asset_url} alt={source.visual_id || ref} className="max-h-72 w-full object-contain" />
        </figure>
      )}

      <div className="mt-3 max-h-96 overflow-y-auto rounded-md bg-muted/20 border border-border/50 p-4 select-text">
        <SourceContentRenderer content={source.content || ''} />
      </div>

      {source.visual_id && (
        <div className="mt-2 text-[10px] text-muted-foreground">
          Visual ID: <span className="font-mono font-semibold">{source.visual_id}</span>
        </div>
      )}
    </article>
  )
}

export default function PDFViewer() {
  const { sources, currentSource } = useStore()
  const containerRef = useRef<HTMLDivElement>(null)
  const activeRef = currentSource ? sourceRef(currentSource, currentSource.id) : ''
  const uniqueSources = useMemo(() => {
    const seen = new Set<string>()
    return sources.filter((source) => {
      const key = source.ref_id || source.citation_id || `${source.id}-${source.kind || 'text'}-${source.visual_id || ''}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }, [sources])
  const activeSourceInList = Boolean(activeRef && uniqueSources.some((source) => sourceRef(source, source.id) === activeRef))
  const displaySources = useMemo(() => {
    if (!activeSourceInList) return uniqueSources
    return [...uniqueSources].sort((a, b) => {
      const aActive = sourceRef(a, a.id) === activeRef
      const bActive = sourceRef(b, b.id) === activeRef
      return Number(bActive) - Number(aActive)
    })
  }, [activeRef, activeSourceInList, uniqueSources])

  useEffect(() => {
    if (!currentSource || !containerRef.current) return
    const ref = sourceRef(currentSource, currentSource.id)
    const target = containerRef.current.querySelector(`[data-source-ref="${CSS.escape(ref)}"]`) as HTMLElement | null
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [currentSource])

  if (!uniqueSources.length) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
        <div>
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FileText size={22} />
          </div>
          <p className="font-semibold text-foreground">No active citations yet</p>
          <p className="mt-1 text-xs">Ask a question, then click an inline citation to inspect the source here.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <header className="border-b border-border/60 bg-card px-4 py-3">
        <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Citation Content</div>
        <div className="mt-1 flex items-center gap-2 text-sm font-semibold text-foreground">
          <span>{activeSourceInList ? `Active source [${activeRef}]` : `${uniqueSources.length} sources`}</span>
          {activeSourceInList && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-bold uppercase text-primary">highlighted</span>}
        </div>
      </header>
      <div ref={containerRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {displaySources.map((source) => (
          <SourceCard
            key={source.ref_id || source.citation_id || `${source.id}-${source.kind || 'text'}-${source.visual_id || ''}`}
            source={source}
            active={isSameSource(currentSource, source)}
          />
        ))}
      </div>
    </div>
  )
}
