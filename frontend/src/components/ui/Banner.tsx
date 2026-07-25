import { CloseIcon } from './Icons'

interface BannerProps {
  message: string
  onDismiss?: () => void
  tone?: 'error' | 'info'
}

export function Banner({ message, onDismiss, tone = 'error' }: BannerProps) {
  return (
    <div className={`banner banner-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span>{message}</span>
      {onDismiss && (
        <button type="button" className="icon-button" onClick={onDismiss} aria-label="Dismiss">
          <CloseIcon width={14} height={14} />
        </button>
      )}
    </div>
  )
}
