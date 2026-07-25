import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { PencilIcon, TrashIcon } from '@/components/ui/Icons'
import type { ConversationSummary } from '@/types'

interface ConversationItemProps {
  conversation: ConversationSummary
  active: boolean
  onSelect: () => void
  onDelete: () => void
  onRename: (title: string) => void
}

export function ConversationItem({
  conversation,
  active,
  onSelect,
  onDelete,
  onRename,
}: ConversationItemProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(conversation.title)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [editing])

  // Keep the draft aligned with server-side renames while not editing.
  useEffect(() => {
    if (!editing) setDraft(conversation.title)
  }, [conversation.title, editing])

  const commitRename = () => {
    const trimmed = draft.trim()
    if (trimmed && trimmed !== conversation.title) onRename(trimmed)
    else setDraft(conversation.title)
    setEditing(false)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      commitRename()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      setDraft(conversation.title)
      setEditing(false)
    }
  }

  if (editing) {
    return (
      <li className="conversation-item editing">
        <input
          ref={inputRef}
          className="conversation-rename-input"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commitRename}
          onKeyDown={handleKeyDown}
          aria-label="Conversation title"
        />
      </li>
    )
  }

  return (
    <li className={active ? 'conversation-item active' : 'conversation-item'}>
      <button
        type="button"
        className="conversation-button"
        onClick={onSelect}
        aria-current={active ? 'true' : undefined}
        title={conversation.title}
      >
        <span className="conversation-title">{conversation.title || 'Untitled'}</span>
      </button>

      {confirmingDelete ? (
        <span className="conversation-confirm">
          <button
            type="button"
            className="conversation-confirm-yes"
            onClick={onDelete}
            aria-label={`Confirm deleting ${conversation.title}`}
          >
            Delete
          </button>
          <button
            type="button"
            className="conversation-confirm-no"
            onClick={() => setConfirmingDelete(false)}
            aria-label="Cancel delete"
          >
            Keep
          </button>
        </span>
      ) : (
        <span className="conversation-actions">
          <button
            type="button"
            className="icon-button"
            onClick={() => setEditing(true)}
            aria-label={`Rename ${conversation.title}`}
          >
            <PencilIcon width={15} height={15} />
          </button>
          <button
            type="button"
            className="icon-button icon-button-danger"
            onClick={() => setConfirmingDelete(true)}
            aria-label={`Delete ${conversation.title}`}
          >
            <TrashIcon width={15} height={15} />
          </button>
        </span>
      )}
    </li>
  )
}
