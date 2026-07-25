import { useState } from 'react'
import { useChat } from '@/context/ChatContext'
import { MessageList } from './MessageList'
import { ChatInput } from './ChatInput'
import { Banner } from '@/components/ui/Banner'
import { MenuIcon } from '@/components/ui/Icons'

interface ChatWindowProps {
  onOpenSidebar: () => void
}

export function ChatWindow({ onOpenSidebar }: ChatWindowProps) {
  const {
    conversations,
    activeId,
    messages,
    loadingMessages,
    streaming,
    error,
    submitMessage,
    cancelStreaming,
    dismissError,
  } = useChat()

  // Bumped on each pick so choosing the same suggestion twice still re-fills.
  const [preset, setPreset] = useState<{ text: string; nonce: number } | null>(null)

  const activeTitle = conversations.find((item) => item.id === activeId)?.title ?? 'New chat'

  return (
    <main className="chat-window">
      <header className="chat-header">
        <button
          type="button"
          className="icon-button chat-menu-button"
          onClick={onOpenSidebar}
          aria-label="Open sidebar"
        >
          <MenuIcon />
        </button>
        <h1 className="chat-title">{activeTitle}</h1>
      </header>

      {error && <Banner message={error} onDismiss={dismissError} />}

      <MessageList
        messages={messages}
        loading={loadingMessages}
        streaming={streaming}
        onPickSuggestion={(text) => setPreset({ text, nonce: Date.now() })}
      />

      <ChatInput
        streaming={streaming}
        presetValue={preset?.text}
        presetNonce={preset?.nonce}
        onSubmit={(content) => void submitMessage(content)}
        onCancel={cancelStreaming}
      />
    </main>
  )
}
