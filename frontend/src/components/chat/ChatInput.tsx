import { useEffect, useState, type KeyboardEvent } from 'react'
import { useAutosizeTextarea } from '@/hooks/useAutosizeTextarea'
import { SendIcon, StopIcon } from '@/components/ui/Icons'

interface ChatInputProps {
  streaming: boolean
  /** Prompt injected from the empty-state suggestions. */
  presetValue?: string
  /**
   * Changes each time a suggestion is picked. The effect keys off this rather
   * than the text so choosing the same suggestion twice still re-fills the box.
   */
  presetNonce?: number
  onSubmit: (content: string) => void
  onCancel: () => void
}

export function ChatInput({
  streaming,
  presetValue,
  presetNonce,
  onSubmit,
  onCancel,
}: ChatInputProps) {
  const [value, setValue] = useState('')
  const textareaRef = useAutosizeTextarea(value)

  // Suggestions pre-fill the box rather than sending immediately, so the user can
  // edit the prompt before committing to it.
  useEffect(() => {
    if (presetNonce === undefined || !presetValue) return
    setValue(presetValue)
    textareaRef.current?.focus()
    // presetValue is deliberately not a dependency; the nonce drives this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetNonce])

  const submit = () => {
    const trimmed = value.trim()
    if (!trimmed || streaming) return
    onSubmit(trimmed)
    setValue('')
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline. IME composition must not be
    // interrupted, or committing a character would send the message.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="composer">
      <div className="composer-inner">
        <textarea
          ref={textareaRef}
          className="composer-textarea"
          rows={1}
          value={value}
          placeholder={streaming ? 'Waiting for the reply…' : 'Message ChatJippity…'}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="Message"
        />

        {streaming ? (
          <button
            type="button"
            className="composer-button composer-button-stop"
            onClick={onCancel}
            aria-label="Stop generating"
            title="Stop generating"
          >
            <StopIcon width={16} height={16} />
          </button>
        ) : (
          <button
            type="button"
            className="composer-button"
            onClick={submit}
            disabled={!value.trim()}
            aria-label="Send message"
            title="Send message"
          >
            <SendIcon width={16} height={16} />
          </button>
        )}
      </div>

      <p className="composer-hint">
        Enter to send · Shift+Enter for a new line
      </p>
    </div>
  )
}
