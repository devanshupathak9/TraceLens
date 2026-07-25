interface SpinnerProps {
  size?: number
  label?: string
}

export function Spinner({ size = 18, label }: SpinnerProps) {
  return (
    <span className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" style={{ width: size, height: size }} />
      {label ? <span className="spinner-label">{label}</span> : <span className="sr-only">Loading</span>}
    </span>
  )
}

/** Three-dot pulse shown while waiting for the model's first token. */
export function TypingDots() {
  return (
    <span className="typing" aria-label="Assistant is typing">
      <span />
      <span />
      <span />
    </span>
  )
}
