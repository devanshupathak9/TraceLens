import { useEffect, useState } from 'react'
import { AuthProvider, useAuth } from '@/context/AuthContext'
import { ChatProvider } from '@/context/ChatContext'
import { AuthScreen } from '@/components/auth/AuthScreen'
import { Sidebar } from '@/components/sidebar/Sidebar'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { Dashboard } from '@/components/dashboard/Dashboard'
import { Spinner } from '@/components/ui/Spinner'
import { useTheme } from '@/hooks/useTheme'

export default function App() {
  return (
    <AuthProvider>
      <Root />
    </AuthProvider>
  )
}

function Root() {
  const { user, initialising } = useAuth()
  const { theme, toggleTheme } = useTheme()

  if (initialising) {
    return (
      <div className="boot-screen">
        <Spinner size={22} label="Starting ChatJippity" />
      </div>
    )
  }

  if (!user) return <AuthScreen />

  return (
    <ChatProvider>
      <Shell theme={theme} onToggleTheme={toggleTheme} />
    </ChatProvider>
  )
}

interface ShellProps {
  theme: ReturnType<typeof useTheme>['theme']
  onToggleTheme: () => void
}

function Shell({ theme, onToggleTheme }: ShellProps) {
  // Only meaningful below the mobile breakpoint, where the sidebar overlays the
  // chat; on desktop it is always visible and this state is inert.
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [view, setView] = useState<'chat' | 'dashboard'>('chat')

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSidebarOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <div className="app-shell">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        theme={theme}
        onToggleTheme={onToggleTheme}
        onOpenDashboard={() => setView('dashboard')}
        onOpenChat={() => setView('chat')}
      />

      {sidebarOpen && (
        <div
          className="scrim"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {view === 'chat' ? (
        <ChatWindow onOpenSidebar={() => setSidebarOpen(true)} />
      ) : (
        <Dashboard onOpenSidebar={() => setSidebarOpen(true)} />
      )}
    </div>
  )
}
