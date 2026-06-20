import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface UIState {
  sidebarCollapsed: boolean
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleSidebar: () => void
  sidebarWidth: number
  setSidebarWidth: (width: number) => void
  rightPanelCollapsed: boolean
  setRightPanelCollapsed: (collapsed: boolean) => void
  toggleRightPanel: () => void
  rightPanelWidth: number
  setRightPanelWidth: (width: number) => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      sidebarWidth: 280,
      setSidebarWidth: (sidebarWidth) => set({ sidebarWidth }),
      rightPanelCollapsed: false,
      setRightPanelCollapsed: (rightPanelCollapsed) => set({ rightPanelCollapsed }),
      toggleRightPanel: () => set((s) => ({ rightPanelCollapsed: !s.rightPanelCollapsed })),
      rightPanelWidth: 450,
      setRightPanelWidth: (rightPanelWidth) => set({ rightPanelWidth }),
    }),
    { name: 'scientific-rag-ui-storage' },
  ),
)

