import { useMemo } from 'react'
import { ConversationItem } from './ConversationItem'
import { Spinner } from '@/components/ui/Spinner'
import { relativeGroup } from '@/lib/format'
import type { ConversationSummary } from '@/types'

interface ConversationListProps {
  conversations: ConversationSummary[]
  activeId: number | null
  loading: boolean
  onSelect: (id: number) => void
  onDelete: (id: number) => void
  onRename: (id: number, title: string) => void
}

export function ConversationList({
  conversations,
  activeId,
  loading,
  onSelect,
  onDelete,
  onRename,
}: ConversationListProps) {
  // Bucket by recency, preserving the server's newest-first ordering within each
  // group so the sidebar reads like ChatGPT's.
  const groups = useMemo(() => {
    const buckets = new Map<string, ConversationSummary[]>()
    for (const conversation of conversations) {
      const label = relativeGroup(conversation.last_active_at)
      const existing = buckets.get(label)
      if (existing) existing.push(conversation)
      else buckets.set(label, [conversation])
    }
    return Array.from(buckets.entries())
  }, [conversations])

  if (loading && conversations.length === 0) {
    return (
      <div className="sidebar-placeholder">
        <Spinner size={16} label="Loading chats" />
      </div>
    )
  }

  if (conversations.length === 0) {
    return (
      <div className="sidebar-placeholder">
        <p>No conversations yet.</p>
        <p className="muted">Start one and it'll show up here.</p>
      </div>
    )
  }

  return (
    <nav className="conversation-scroll" aria-label="Conversations">
      {groups.map(([label, items]) => (
        <div key={label} className="conversation-group">
          <h2 className="conversation-group-label">{label}</h2>
          <ul className="conversation-list">
            {items.map((conversation) => (
              <ConversationItem
                key={conversation.id}
                conversation={conversation}
                active={conversation.id === activeId}
                onSelect={() => onSelect(conversation.id)}
                onDelete={() => onDelete(conversation.id)}
                onRename={(title) => onRename(conversation.id, title)}
              />
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}
