import { TypingDots } from '@/components/ui/Spinner'
import { SparkIcon, UserIcon } from '@/components/ui/Icons'
import { formatTime } from '@/lib/format'
import type { Message } from '@/types'

interface MessageBubbleProps {
  message: Message
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const streaming = message.status === 'streaming'
  const awaitingFirstToken = streaming && message.content.length === 0

  return (
    <article className={`message message-${isUser ? 'user' : 'assistant'}`}>
      <span className="message-avatar" aria-hidden="true">
        {isUser ? <UserIcon width={16} height={16} /> : <SparkIcon width={16} height={16} />}
      </span>

      <div className="message-body">
        <header className="message-meta">
          <span className="message-role">{isUser ? 'You' : 'Assistant'}</span>
          {!streaming && message.created_at && (
            <time dateTime={message.created_at}>{formatTime(message.created_at)}</time>
          )}
        </header>

        {awaitingFirstToken ? (
          <TypingDots />
        ) : (
          <div className="message-content">
            {/* Rendered as plain text on purpose: no markdown parser means no
                dangerouslySetInnerHTML, so model output can't inject markup. */}
            {message.content}
            {streaming && <span className="cursor" aria-hidden="true" />}
          </div>
        )}

        {message.status === 'cancelled' && (
          <p className="message-note">Stopped by you.</p>
        )}

        {message.status === 'error' && (
          <p className="message-note message-note-error">
            {message.error ?? 'Something went wrong generating this reply.'}
          </p>
        )}
      </div>
    </article>
  )
}
