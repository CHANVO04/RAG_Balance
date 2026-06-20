import { SourceInfo } from '../../store'
import { FileText } from 'lucide-react'
import { sourceRef } from '../../lib/citationUtils'

interface Props {
  source: SourceInfo
  onClick: (source: SourceInfo) => void
}

export default function SourcePill({ source, onClick }: Props) {
  const label = sourceRef(source, source.id)
  return (
    <button
      onClick={() => onClick(source)}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-blue-50 text-blue-600 border border-blue-200 rounded hover:bg-blue-100 transition-colors"
      title={`${source.file_name} — Trang ${source.page}`}
    >
      <FileText size={10} />
      [{label}]
    </button>
  )
}
