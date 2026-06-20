import Sidebar from '../shared/Sidebar'
import { useThemeStore } from '../../store/themeStore'
import { useWorkspaceStore } from '../../store/workspaceStore'
import { cn } from '../../lib/utils'

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const { theme } = useThemeStore()
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  
  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0]
  const isSetupComplete = activeWorkspace?.isSetupComplete ?? false

  return (
    <div className={cn(
      "flex h-screen w-full overflow-hidden bg-background text-foreground font-sans",
      theme === 'dark' && "dark"
    )}>
      {isSetupComplete && <Sidebar />}
      <main className="flex-1 flex flex-col min-w-0 bg-background relative overflow-hidden">
        {children}
      </main>
    </div>
  )
}
