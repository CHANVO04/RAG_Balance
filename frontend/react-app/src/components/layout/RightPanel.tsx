import React from 'react'
import { useStore } from '../../store'
import { FileText, Network, Activity, BookOpen, ChevronRight, ChevronLeft, LayoutDashboard } from 'lucide-react'
import PDFViewer from '../pdf/PDFViewer'
import OriginalPDFViewer from '../pdf/OriginalPDFViewer'
import KGGraph from '../kg/KGGraph'
import AnalyticsDashboard from '../analytics/AnalyticsDashboard'
import UMAPSpace from '../umap/UMAPSpace'
import SearchSettings from '../chat/SearchSettings'
import ErrorBoundary from '../ui/ErrorBoundary'
import { useUIStore } from '../../store/uiStore'
import { cn } from '../../lib/utils'
import { motion, AnimatePresence } from 'framer-motion'

const TABS = [
  { key: 'docs', label: 'Document', Icon: BookOpen  },
  { key: 'pdf',  label: 'Content',  Icon: FileText  },
  { key: 'kg',   label: 'Graph',    Icon: Network   },
  { key: 'umap', label: 'Query',    Icon: LayoutDashboard },
  { key: 'analytics', label: 'Stats', Icon: Activity },
] as const

export default function RightPanel() {
  const { rightTab, setRightTab } = useStore()
  const { rightPanelWidth, setRightPanelWidth, rightPanelCollapsed: collapsed, toggleRightPanel } = useUIStore()
  const [isDragging, setIsDragging] = React.useState(false)
  const [dragWidth, setDragWidth] = React.useState<number | null>(null)
  const frameRef = React.useRef<number | null>(null)
  const pendingWidthRef = React.useRef(rightPanelWidth)
  const activeWidth = collapsed ? 64 : (dragWidth ?? rightPanelWidth)

  React.useEffect(() => {
    return () => {
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current)
      }
    }
  }, [])

  const scheduleWidthUpdate = (width: number) => {
    pendingWidthRef.current = width
    if (frameRef.current !== null) return

    frameRef.current = window.requestAnimationFrame(() => {
      setDragWidth(pendingWidthRef.current)
      frameRef.current = null
    })
  }

  const resizeFromClientX = (clientX: number) => {
    const newWidth = Math.max(320, Math.min(800, window.innerWidth - clientX))
    scheduleWidthUpdate(newWidth)
  }

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (collapsed) return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    pendingWidthRef.current = rightPanelWidth
    setDragWidth(rightPanelWidth)
    setIsDragging(true)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  const finishResize = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
    if (frameRef.current !== null) {
      window.cancelAnimationFrame(frameRef.current)
      frameRef.current = null
    }
    setRightPanelWidth(pendingWidthRef.current)
    setDragWidth(null)
    setIsDragging(false)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  return (
    <motion.aside 
      animate={{ width: activeWidth }}
      transition={isDragging ? { duration: 0 } : { type: 'tween', ease: 'easeOut', duration: 0.2 }}
      className="flex-shrink-0 border-l border-border/50 glass flex flex-col relative z-20 shadow-2xl group overflow-hidden"
    >
      {/* Resize handle (only when expanded) */}
      {!collapsed && (
        <div
          onPointerDown={handlePointerDown}
          onPointerMove={(e) => {
            if (isDragging) resizeFromClientX(e.clientX)
          }}
          onPointerUp={finishResize}
          onPointerCancel={finishResize}
          className={cn(
            "absolute left-0 top-0 bottom-0 w-2 touch-none cursor-col-resize hover:bg-primary/50 transition-colors z-50",
            isDragging ? "bg-primary" : "bg-transparent group-hover:bg-border/30"
          )}
        />
      )}

      {isDragging && <div className="absolute inset-0 z-40 cursor-col-resize bg-transparent" />}

      {/* Expanded Tab bar */}
      {!collapsed ? (
        <div className="flex p-2 gap-1 bg-background/50 border-b border-border/50 items-center justify-between">
          <button 
            onClick={toggleRightPanel}
            className="p-1.5 rounded-lg hover:bg-accent text-muted-foreground transition-colors shrink-0"
            title="Collapse Panel"
          >
            <ChevronRight size={18} />
          </button>

          <div className="flex flex-1 gap-1">
            {TABS.map(({ key, label, Icon }) => (
              <button
                key={key}
                onClick={() => setRightTab(key as any)}
                className={cn(
                  "flex-1 flex items-center justify-center py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider gap-2 transition-all",
                  rightTab === key
                    ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                )}
              >
                <Icon size={14} />
                {activeWidth >= 480 && (
                  <span className="transition-all duration-200">{label}</span>
                )}
              </button>
            ))}
          </div>
        </div>
      ) : (
        /* Collapsed Tab bar (Vertical) */
        <div className="flex flex-col items-center py-4 gap-4 h-full bg-background/50 border-b border-border/50">
          <button 
            onClick={toggleRightPanel}
            className="p-1.5 rounded-lg hover:bg-accent text-muted-foreground transition-colors shrink-0"
            title="Expand Panel"
          >
            <ChevronLeft size={18} />
          </button>
          
          <div className="flex flex-col gap-2 w-full px-2">
            {TABS.map(({ key, Icon }) => (
              <button
                key={key}
                onClick={() => {
                  setRightTab(key as any)
                  toggleRightPanel() // Expand on tab click! This is extremely smart UX!
                }}
                className={cn(
                  "w-12 h-12 flex items-center justify-center rounded-xl transition-all",
                  rightTab === key
                    ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                )}
              >
                <Icon size={18} />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Tab content (only when expanded) */}
      {!collapsed && (
        <div className={cn("flex-1 min-h-0 overflow-hidden bg-background", isDragging && "pointer-events-none")}>
          <AnimatePresence mode="wait">
            <motion.div
              key={rightTab}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
              className="h-full min-h-0 overflow-y-auto"
            >
              {rightTab === 'pdf'  && (
                <ErrorBoundary fallbackLabel="Failed to load PDF Viewer">
                  <PDFViewer />
                </ErrorBoundary>
              )}
              {rightTab === 'kg'   && (
                <ErrorBoundary fallbackLabel="Failed to load Knowledge Graph">
                  <div className="h-full"><KGGraph /></div>
                </ErrorBoundary>
              )}
              {rightTab === 'umap' && (
                <ErrorBoundary fallbackLabel="Failed to load Query Trace">
                  <div className="min-h-full w-full space-y-4 p-6 pb-28">
                    <SearchSettings />
                    <UMAPSpace />
                  </div>
                </ErrorBoundary>
              )}
              {rightTab === 'analytics' && (
                <ErrorBoundary fallbackLabel="Failed to load Analytics">
                  <AnalyticsDashboard />
                </ErrorBoundary>
              )}
              {rightTab === 'docs' && (
                <ErrorBoundary fallbackLabel="Failed to load PDF Viewer">
                  <OriginalPDFViewer />
                </ErrorBoundary>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      )}
    </motion.aside>
  )
}
