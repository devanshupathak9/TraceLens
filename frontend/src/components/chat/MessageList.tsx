import { MessageBubble } from './MessageBubble'
import { EmptyState } from './EmptyState'
import { Spinner } from '@/components/ui/Spinner'
import { ArrowDownIcon } from '@/components/ui/Icons'
import { useAutoScroll } from '@/hooks/useAutoScroll'
import type { Message } from '@/types'

interface MessageListProps {
  messages: Message[]
  loading: boolean
  streaming: boolean
  onPickSuggestion: (prompt: string) => void
}

export function MessageList({
  messages,
  loading,
  streaming,
  onPickSuggestion,
}: MessageListProps) {
  // Re-pin on both message count and streamed length so scrolling follows tokens
  // as they arrive, not just whole messages.
  const scrollKey = `${messages.length}:${messages[messages.length - 1]?.content.length ?? 0}`
  const { containerRef, handleScroll, scrollToBottom, showJumpButton } = useAutoScroll(scrollKey)

  if (loading) {
    return (
      <div className="message-scroll">
        <div className="centered-state">
          <Spinner label="Loading conversation" />
        </div>
      </div>
    )
  }

  if (messages.length === 0) {
    return (
      <div className="message-scroll">
        <EmptyState onPick={onPickSuggestion} disabled={streaming} />
      </div>
    )
  }

  return (
    <div className="message-scroll-wrapper">
      <div className="message-scroll" ref={containerRef} onScroll={handleScroll}>
        <div className="message-thread">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
        </div>
      </div>

      {showJumpButton && (
        <button
          type="button"
          className="jump-button"
          onClick={() => scrollToBottom()}
          aria-label="Scroll to latest message"
        >
          <ArrowDownIcon width={16} height={16} />
        </button>
      )}
    </div>
  )
}
