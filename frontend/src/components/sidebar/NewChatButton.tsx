import { PlusIcon } from '@/components/ui/Icons'

interface NewChatButtonProps {
  onClick: () => void
  disabled?: boolean
}

export function NewChatButton({ onClick, disabled }: NewChatButtonProps) {
  return (
    <button type="button" className="new-chat-button" onClick={onClick} disabled={disabled}>
      <PlusIcon />
      <span>New chat</span>
    </button>
  )
}
