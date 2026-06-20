import { useEffect, useState } from 'react'
import { useStore } from './store'
import { useWorkspaceStore } from './store/workspaceStore'
import MainLayout from './components/layout/MainLayout'
import CenterPanel from './components/layout/CenterPanel'
import RightPanel from './components/layout/RightPanel'
import WorkspaceSetupWizard from './components/shared/WorkspaceSetupWizard'
import { useIngestPoll } from './hooks/useIngestPoll'
import Toaster from './components/ui/Toaster'
import SplashScreen from './components/shared/SplashScreen'

export default function App() {
  useIngestPoll()
  const newConversation = useStore((s) => s.newConversation)
  const conversations   = useStore((s) => s.conversations)
  const activeConversationByWorkspace = useStore((s) => s.activeConversationByWorkspace)
  const activeConversationId = useStore((s) => s.activeConversationId)
  const setActiveConversation = useStore((s) => s.setActiveConversation)
  
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  
  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0]
  const isSetupComplete = activeWorkspace?.isSetupComplete ?? false

  // Session-based splash screen guard
  const [showSplash, setShowSplash] = useState(() => {
    try {
      return !sessionStorage.getItem('rag_splash_shown')
    } catch {
      return true
    }
  })

  const handleSplashComplete = () => {
    setShowSplash(false)
    try {
      sessionStorage.setItem('rag_splash_shown', 'true')
    } catch {
      // Ignore sessionStorage issues
    }
  }

  useEffect(() => {
    if (!isSetupComplete) return

    const activeForWorkspace = activeConversationByWorkspace[activeWorkspaceId]
    if (activeForWorkspace) {
      if (activeConversationId !== activeForWorkspace) {
        setActiveConversation(activeForWorkspace)
      }
      return
    }

    const existing = conversations.find((c) => c.workspaceId === activeWorkspaceId)
    if (existing) {
      if (activeConversationId !== existing.id) {
        setActiveConversation(existing.id)
      }
      return
    }

    newConversation(activeWorkspaceId)
  }, [activeConversationId, activeWorkspaceId, activeConversationByWorkspace, conversations, newConversation, setActiveConversation, isSetupComplete])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '/' && (e.target as HTMLElement).tagName !== 'INPUT' && (e.target as HTMLElement).tagName !== 'TEXTAREA') {
        e.preventDefault()
        const input = document.querySelector('[data-chat-input="true"]') as HTMLTextAreaElement | null
        input?.focus()
      }
      
      if (e.key === 'Escape') {
        (document.activeElement as HTMLElement)?.blur()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <MainLayout>
      <div className="flex h-full w-full overflow-hidden relative">
        {/* Ambient Glow Layers behind panels */}
        <div className="ambient-glow-wrapper">
          <div className="ambient-glow-1" />
          <div className="ambient-glow-2" />
        </div>

        {/* Mobile guard */}
        <div className="min-[500px]:hidden absolute inset-0 z-[100] bg-background flex items-center justify-center p-8 text-center">
          <div className="space-y-4">
            <div className="text-4xl">SR</div>
            <h2 className="text-xl font-bold">Scientific RAG</h2>
            <p className="text-sm text-muted-foreground">Please use a wider window or desktop viewport for the best experience (min 500px).</p>
          </div>
        </div>

        {/* Desktop View */}
        <div className="hidden min-[500px]:flex flex-1 overflow-hidden z-10">
          {isSetupComplete ? (
            <>
              <CenterPanel />
              <RightPanel />
            </>
          ) : (
            <WorkspaceSetupWizard />
          )}
        </div>

        {/* High performance animated splash screen overlay */}
        {showSplash && <SplashScreen onComplete={handleSplashComplete} />}
      </div>
      <Toaster />
    </MainLayout>
  )
}
