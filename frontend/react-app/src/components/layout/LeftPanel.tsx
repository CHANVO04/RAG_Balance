import { useStore } from '../../store'
import { Plus, MessageSquare, Cpu } from 'lucide-react'
import { useWorkspaceStore } from '../../store/workspaceStore'

export default function LeftPanel() {
  const { conversations, activeConversationId, newConversation, setActiveConversation } = useStore()
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)

  return (
    <aside className="w-64 flex-shrink-0 border-r border-gray-200 bg-gray-50 flex flex-col">
      <div className="p-3 border-b border-gray-200">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-6 h-6 bg-blue-600 rounded-md flex items-center justify-center">
            <Cpu size={13} className="text-white" />
          </div>
          <h1 className="text-sm font-semibold text-blue-700">Scientific RAG</h1>
        </div>
        <button
          onClick={() => newConversation(activeWorkspaceId)}
          className="w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
        >
          <Plus size={14} /> New conversation
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto p-2 space-y-1">
        {conversations.filter((c) => c.workspaceId === activeWorkspaceId).map((c) => (
          <button
            key={c.id}
            onClick={() => setActiveConversation(c.id)}
            className={`w-full flex items-center gap-2 px-3 py-2 text-xs rounded-lg text-left transition-colors ${
              c.id === activeConversationId
                ? 'bg-blue-100 text-blue-700'
                : 'hover:bg-gray-200 text-gray-600'
            }`}
          >
            <MessageSquare size={12} className="flex-shrink-0" />
            <span className="truncate">{c.title}</span>
          </button>
        ))}
      </nav>
    </aside>
  )
}
