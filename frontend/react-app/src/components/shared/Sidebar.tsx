import React from 'react'
import { 
  MessageSquare, 
  Files, 
  Settings, 
  ChevronLeft, 
  ChevronRight, 
  LogOut,
  Moon,
  Sun,
  Trash2,
  Database,
  Search,
  X,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { useThemeStore } from '../../store/themeStore'
import { useStore } from '../../store'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { useUIStore } from '../../store/uiStore'
import WorkspaceSwitcher from './WorkspaceSwitcher'
import SidebarDocumentManager from './SidebarDocumentManager'
import { motion } from 'framer-motion'
import ConfirmDialog from '../ui/ConfirmDialog'

export default function Sidebar() {
  const { sidebarCollapsed: collapsed, toggleSidebar, sidebarWidth, setSidebarWidth } = useUIStore()
  const { theme, toggleTheme } = useThemeStore()
  const { activeWorkspaceId } = useWorkspaceStore()
  const { conversations, activeConversationId, setActiveConversation, newConversation, setRightTab, deleteConversation } = useStore()
  const [isDragging, setIsDragging] = React.useState(false)
  const [showAllChats, setShowAllChats] = React.useState(false)
  const [chatSearchQuery, setChatSearchQuery] = React.useState('')
  const [pendingDeleteChatId, setPendingDeleteChatId] = React.useState<string | null>(null)

  // Filter conversations by workspace
  const filteredConversationsByWorkspace = conversations.filter(c => c.workspaceId === activeWorkspaceId)
  
  // Filter by search query if expanded
  const filteredConversations = React.useMemo(() => {
    if (!showAllChats || !chatSearchQuery.trim()) return filteredConversationsByWorkspace
    const q = chatSearchQuery.toLowerCase()
    return filteredConversationsByWorkspace.filter(c => 
      c.title.toLowerCase().includes(q) || 
      (c.title === 'Cuộc trò chuyện mới' ? 'new conversation' : c.title.toLowerCase()).includes(q)
    )
  }, [filteredConversationsByWorkspace, showAllChats, chatSearchQuery])

  const visibleConversations = showAllChats 
    ? filteredConversations 
    : filteredConversationsByWorkspace.slice(0, 5)

  const displayConversationTitle = (title: string) =>
    title === 'Cuộc trò chuyện mới' ? 'New conversation' : title

  const pendingDeleteChat = conversations.find((conv) => conv.id === pendingDeleteChatId)

  const navItems = [
    { icon: MessageSquare, label: 'Chat', id: 'chat' },
    { icon: Files, label: 'Document', id: 'docs' },
    { icon: Database, label: 'Knowledge Graph', id: 'kg' },
  ]

  const handleMouseDown = (e: React.MouseEvent) => {
    if (collapsed) return
    e.preventDefault()
    setIsDragging(true)
    
    const handleMouseMove = (moveEvent: MouseEvent) => {
      const newWidth = Math.max(200, Math.min(450, moveEvent.clientX))
      setSidebarWidth(newWidth)
    }
    
    const handleMouseUp = () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
      setIsDragging(false)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  return (
    <motion.aside
      animate={{ width: collapsed ? 80 : sidebarWidth }}
      transition={isDragging ? { duration: 0 } : { type: 'tween', ease: 'easeOut', duration: 0.2 }}
      className={cn(
        "flex flex-col h-screen glass border-r border-border/50 relative group",
        collapsed ? "items-center" : "items-stretch"
      )}
    >
      {/* Logo & Toggle */}
      <div className="p-4 flex items-center justify-between border-b border-border/30">
        {!collapsed && (
          <div className="flex items-center gap-2 font-bold text-lg tracking-tight select-none">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground shadow-lg shadow-primary/20">
              S
            </div>
            <span>Scientific <span className="text-primary">RAG</span></span>
          </div>
        )}
        <button 
          onClick={toggleSidebar}
          className="p-1.5 rounded-lg hover:bg-accent text-muted-foreground transition-colors"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      {/* Workspace Selector */}
      <WorkspaceSwitcher collapsed={collapsed} />

      {/* Main Nav */}
      <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto overflow-x-hidden">
        <div className="px-1">
          <SidebarDocumentManager collapsed={collapsed} />
        </div>

        <div className="h-4" />

        <motion.button
          whileHover={{ y: -1 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => newConversation(activeWorkspaceId)}
          className={cn(
            "flex items-center gap-3 w-full min-h-12 p-2.5 rounded-xl font-bold transition-all active:scale-[0.98]",
            "btn-glass border border-cyan-500/20 hover:btn-glass-active shadow-md hover:shadow-lg",
            collapsed ? "justify-center" : "px-4"
          )}
        >
          <MessageSquare size={18} className="shrink-0" />
          {!collapsed && <span className="whitespace-nowrap">New Chat</span>}
        </motion.button>

        <div className="h-4" />

        {/* History / Sessions */}
        {!collapsed && (
          <div className="flex items-center justify-between text-[10px] font-bold text-muted-foreground px-2 py-2 uppercase tracking-wider select-none">
            <span>Recent Chats</span>
            {showAllChats && (
              <span className="text-[9px] text-cyan-500 font-extrabold capitalize">
                ({filteredConversationsByWorkspace.length})
              </span>
            )}
          </div>
        )}

        {/* Search input (when expanded and not collapsed sidebar) */}
        {!collapsed && showAllChats && (
          <div className="px-2 mb-3">
            <div className="relative flex items-center">
              <Search className="absolute left-3 w-3.5 h-3.5 text-muted-foreground/60" />
              <input
                type="text"
                placeholder="Search chats..."
                value={chatSearchQuery}
                onChange={(e) => setChatSearchQuery(e.target.value)}
                className="w-full pl-8 pr-7 py-1.5 rounded-lg text-xs bg-accent/30 border border-border/40 text-foreground placeholder-muted-foreground/60 focus:outline-none focus:border-primary/50 transition-colors"
                autoComplete="off"
                autoCorrect="off"
                autoFocus
              />
              {chatSearchQuery && (
                <button
                  onClick={() => setChatSearchQuery('')}
                  className="absolute right-2.5 p-0.5 rounded-full hover:bg-accent text-muted-foreground"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>
        )}

        <div className={cn("space-y-1", showAllChats && "max-h-60 overflow-y-auto pr-1 scrollbar-thin")}>
          {visibleConversations.map((conv) => (
            <motion.button
              key={conv.id}
              whileHover={{ x: collapsed ? 0 : 2 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setActiveConversation(conv.id)}
              className={cn(
                "group flex items-center gap-3 w-full p-2.5 rounded-xl text-sm transition-all relative overflow-hidden",
                activeConversationId === conv.id 
                  ? "bg-gradient-to-r from-blue-600 to-cyan-500 text-white font-semibold shadow-md shadow-primary/20" 
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
              )}
            >
              <MessageSquare size={16} className="shrink-0" />
              {!collapsed && (
                <span className="truncate flex-1 text-left">{displayConversationTitle(conv.title)}</span>
              )}
              {activeConversationId === conv.id && !collapsed && (
                <div className="w-1.5 h-1.5 rounded-full bg-cyan-300 animate-pulse-cyan shrink-0" />
              )}
              {!collapsed && activeConversationId === conv.id && (
                <Trash2 
                  size={14} 
                  className="opacity-0 group-hover:opacity-100 transition-opacity hover:text-white cursor-pointer relative z-30 ml-auto shrink-0" 
                  onClick={(e) => {
                    e.stopPropagation();
                    setPendingDeleteChatId(conv.id);
                  }}
                  aria-label="Delete Conversation"
                />
              )}
            </motion.button>
          ))}
          {!collapsed && showAllChats && filteredConversations.length === 0 && (
            <div className="text-xs text-center text-muted-foreground/60 py-4 italic select-none">
              No chats match search
            </div>
          )}
        </div>

        {/* Expand / Collapse buttons */}
        {!collapsed && filteredConversationsByWorkspace.length > 5 && (
          <div className="px-2 mt-2">
            <button
              onClick={() => {
                setShowAllChats(!showAllChats)
                if (showAllChats) setChatSearchQuery('') // Clear search on collapse
              }}
              className="flex items-center justify-center gap-1.5 w-full py-2 rounded-xl text-xs font-bold text-muted-foreground hover:bg-accent/40 hover:text-foreground transition-all border border-transparent hover:border-border/30 cursor-pointer"
            >
              {showAllChats ? (
                <>
                  <ChevronUp size={14} />
                  <span>Show less</span>
                </>
              ) : (
                <>
                  <ChevronDown size={14} />
                  <span>Show all history (+{filteredConversationsByWorkspace.length - 5})</span>
                </>
              )}
            </button>
          </div>
        )}
      </nav>

      {/* Footer Actions */}
      <div className="p-3 mt-auto border-t border-border/30 z-20">
        {collapsed ? (
          <div className="flex flex-col items-center gap-3 w-full">
            <button
              onClick={() => window.dispatchEvent(new Event('rag:toggle-settings'))}
              className="p-2 rounded-xl text-muted-foreground hover:bg-accent hover:text-foreground hover:scale-105 transition-all duration-150 active:scale-95"
              title="Search Settings"
            >
              <Settings size={16} />
            </button>
            <button
              onClick={toggleTheme}
              className="p-2 rounded-xl text-muted-foreground hover:bg-accent hover:text-foreground hover:scale-105 transition-all duration-150 active:scale-95"
              title={theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
            >
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button
              className="p-2 rounded-xl text-muted-foreground hover:bg-destructive/10 hover:text-destructive hover:scale-105 transition-all duration-150 active:scale-95"
              title="Logout"
            >
              <LogOut size={16} />
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between w-full bg-accent/40 dark:bg-accent/20 rounded-xl p-1 border border-border/30 backdrop-blur-sm shadow-inner">
            <button
              onClick={() => window.dispatchEvent(new Event('rag:toggle-settings'))}
              className="flex-1 flex flex-col items-center justify-center py-2 px-1 rounded-lg text-muted-foreground hover:bg-background/80 hover:text-foreground hover:shadow-sm transition-all duration-200 active:scale-95 cursor-pointer group/footer"
              title="Search Settings"
            >
              <Settings size={15} className="group-hover/footer:rotate-45 transition-transform duration-300" />
              <span className="text-[9px] mt-0.5 font-bold uppercase tracking-wider scale-90 opacity-75">Settings</span>
            </button>
            <div className="w-[1px] h-6 bg-border/40 shrink-0" />
            <button
              onClick={toggleTheme}
              className="flex-1 flex flex-col items-center justify-center py-2 px-1 rounded-lg text-muted-foreground hover:bg-background/80 hover:text-foreground hover:shadow-sm transition-all duration-200 active:scale-95 cursor-pointer"
              title={theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
            >
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
              <span className="text-[9px] mt-0.5 font-bold uppercase tracking-wider scale-90 opacity-75">{theme === 'dark' ? 'Light' : 'Dark'}</span>
            </button>
            <div className="w-[1px] h-6 bg-border/40 shrink-0" />
            <button
              className="flex-1 flex flex-col items-center justify-center py-2 px-1 rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive hover:shadow-sm transition-all duration-200 active:scale-95 cursor-pointer"
              title="Logout"
            >
              <LogOut size={15} />
              <span className="text-[9px] mt-0.5 font-bold uppercase tracking-wider scale-90 opacity-75">Logout</span>
            </button>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={Boolean(pendingDeleteChat)}
        title="Delete chat?"
        description={`This removes "${displayConversationTitle(pendingDeleteChat?.title ?? 'New conversation')}" from local browser history for this workspace.`}
        confirmLabel="Delete chat"
        onCancel={() => setPendingDeleteChatId(null)}
        onConfirm={() => {
          if (!pendingDeleteChatId) return
          deleteConversation(pendingDeleteChatId)
          setPendingDeleteChatId(null)
        }}
      />

      {/* Resize handle */}
      {!collapsed && (
        <div
          onMouseDown={handleMouseDown}
          className={cn(
            "absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-primary/50 transition-colors z-50",
            isDragging ? "bg-primary" : "bg-transparent group-hover:bg-border/30"
          )}
        />
      )}
    </motion.aside>
  )
}
