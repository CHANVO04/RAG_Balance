import { useEffect } from 'react'
import { useStore } from '../../store'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { useQuery } from '@tanstack/react-query'
import { fetchDocuments } from '../../api/query'
import { ExternalLink, FileText } from 'lucide-react'

export default function OriginalPDFViewer() {
  const { currentFile, currentPage, setPDF } = useStore()
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)

  // Fetch documents in the active workspace
  const { data: documents = [], isLoading } = useQuery({
    queryKey: ['documents', activeWorkspaceId],
    queryFn: () => fetchDocuments(activeWorkspaceId)
  })

  // Automatically load the first document if currentFile is not set and documents are available
  useEffect(() => {
    if (!currentFile && documents.length > 0) {
      setPDF(documents[0].file_name, 1)
    }
  }, [currentFile, documents, setPDF])

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground select-none">
        <div className="animate-pulse">Loading documents...</div>
      </div>
    )
  }

  if (documents.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground select-none">
        <div>
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FileText size={22} />
          </div>
          <p className="font-semibold text-foreground">No documents in workspace</p>
          <p className="mt-1 text-xs">
            Ingest documents from the left sidebar to enable PDF viewing.
          </p>
        </div>
      </div>
    )
  }

  // Fallback if currentFile is not in the document list (e.g. deleted or from another workspace)
  const isCurrentFileValid = documents.some(doc => doc.file_name === currentFile)
  const activeFile = isCurrentFileValid ? currentFile : (documents[0]?.file_name || null)
  const activeDocument = documents.find((doc) => doc.file_name === activeFile)
  const totalPages = activeDocument?.total_pages ?? 0

  if (!activeFile) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground select-none">
        <p className="font-semibold text-foreground">Select a document to begin viewing</p>
      </div>
    )
  }

  const fileUrl = activeWorkspaceId === 'default'
    ? `/data/${encodeURIComponent(activeFile)}#page=${currentPage}`
    : `/workspace-data/${encodeURIComponent(activeWorkspaceId)}/data/${encodeURIComponent(activeFile)}#page=${currentPage}`

  const handleOpenNewTab = () => {
    window.open(fileUrl, '_blank', 'noopener,noreferrer')
  }

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setPDF(e.target.value, 1)
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <header className="border-b border-border/60 bg-card px-4 py-3 flex items-center justify-between shadow-sm shrink-0">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="shrink-0 select-none">
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Original Document</div>
          </div>
          <div className="min-w-0 max-w-xs flex-1">
            <select
              value={activeFile}
              onChange={handleSelectChange}
              className="w-full bg-accent/50 text-foreground text-xs font-semibold rounded-lg px-2 py-1.5 border border-border/40 outline-none focus:border-primary/50 cursor-pointer truncate"
              title="Select document to view"
            >
              {documents.map((doc) => (
                <option key={doc.sha256 || doc.file_name} value={doc.file_name}>
                  {doc.file_name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] font-medium bg-primary/10 text-primary px-2 py-0.5 rounded-full">
            {totalPages > 0 ? `${totalPages} Pages` : 'Pages --'}
          </span>
          <button
            onClick={handleOpenNewTab}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:border-primary hover:text-primary"
            title="Open original PDF in a new browser tab"
          >
            <ExternalLink size={14} />
          </button>
        </div>
      </header>
      <div className="flex-1 w-full h-full min-h-0 overflow-hidden bg-muted/20">
        <iframe
          src={fileUrl}
          className="w-full h-full border-none"
          title={`PDF Viewer - ${activeFile}`}
        />
      </div>
    </div>
  )
}
