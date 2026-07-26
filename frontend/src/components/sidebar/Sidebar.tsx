import { useChat } from '@/context/ChatContext'
import { ConversationList } from './ConversationList'
import { NewChatButton } from './NewChatButton'
import { UserMenu } from './UserMenu'
import { ChartIcon, CloseIcon, SparkIcon } from '@/components/ui/Icons'
import type { Theme } from '@/lib/storage'

interface SidebarProps {
  open: boolean
  onClose: () => void
  theme: Theme
  onToggleTheme: () => void
  /** Switches the main pane to the dashboard view. */
  onOpenDashboard: () => void
  /** Switches the main pane back to the chat view. */
  onOpenChat: () => void
}

export function Sidebar({
  open,
  onClose,
  theme,
  onToggleTheme,
  onOpenDashboard,
  onOpenChat,
}: SidebarProps) {
  const {
    conversations,
    activeId,
    loadingList,
    startNewChat,
    selectConversation,
    removeConversation,
    renameConversation,
  } = useChat()

  /** On narrow screens the sidebar overlays the chat, so selecting dismisses it. */
  const selectAndClose = (id: number) => {
    selectConversation(id)
    onOpenChat()
    onClose()
  }

  return (
    <aside className={open ? 'sidebar open' : 'sidebar'} aria-label="Chat history">
      <div className="sidebar-header">
        <span className="sidebar-brand">
          <SparkIcon width={18} height={18} />
          ChatJippity
        </span>
        <button
          type="button"
          className="icon-button sidebar-close"
          onClick={onClose}
          aria-label="Close sidebar"
        >
          <CloseIcon />
        </button>
      </div>

      <div className="sidebar-actions">
        <NewChatButton
          onClick={() => {
            startNewChat()
            onOpenChat()
            onClose()
          }}
        />
        <button
          type="button"
          className="new-chat-button"
          onClick={() => {
            onOpenDashboard()
            onClose()
          }}
        >
          <ChartIcon />
          <span>Dashboard</span>
        </button>
      </div>

      <ConversationList
        conversations={conversations}
        activeId={activeId}
        loading={loadingList}
        onSelect={selectAndClose}
        onDelete={removeConversation}
        onRename={renameConversation}
      />

      <UserMenu theme={theme} onToggleTheme={onToggleTheme} />
    </aside>
  )
}
