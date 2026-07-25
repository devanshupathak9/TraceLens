import { SparkIcon } from '@/components/ui/Icons'

const SUGGESTIONS = [
  'Explain the difference between a queue and a stream.',
  'Write a Python function that retries with exponential backoff.',
  'Summarise the tradeoffs of server-sent events versus WebSockets.',
  'Draft a short release note for a bug fix.',
]

interface EmptyStateProps {
  onPick: (prompt: string) => void
  disabled?: boolean
}

export function EmptyState({ onPick, disabled }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <span className="empty-logo">
        <SparkIcon width={26} height={26} />
      </span>
      <h2>What can I help with?</h2>
      <p className="muted">Ask anything. Your conversation history stays in the sidebar.</p>

      <ul className="suggestions">
        {SUGGESTIONS.map((suggestion) => (
          <li key={suggestion}>
            <button
              type="button"
              className="suggestion"
              onClick={() => onPick(suggestion)}
              disabled={disabled}
            >
              {suggestion}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
