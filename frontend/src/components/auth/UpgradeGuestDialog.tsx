import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useAuth } from '@/context/AuthContext'
import { Spinner } from '@/components/ui/Spinner'
import { CloseIcon } from '@/components/ui/Icons'

interface UpgradeGuestDialogProps {
  onClose: () => void
}

/**
 * Lets a guest attach credentials to the account they're already using, so the
 * chats created while anonymous survive beyond this browser.
 */
export function UpgradeGuestDialog({ onClose }: UpgradeGuestDialogProps) {
  const { upgradeGuest, pending, error, clearError } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const emailRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    emailRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setLocalError(null)
    clearError()

    if (!email.includes('@')) {
      setLocalError('Enter a valid email address.')
      return
    }
    if (password.length < 8) {
      setLocalError('Password must be at least 8 characters.')
      return
    }

    try {
      await upgradeGuest(email, password)
      onClose()
    } catch {
      // Message rendered below from the auth context.
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upgrade-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <h2 id="upgrade-title">Save your chats</h2>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <CloseIcon />
          </button>
        </div>

        <p className="modal-body-text">
          Add an email and password to keep the conversations you've already
          started. Nothing is lost — this upgrades the guest account you're using
          rather than creating a new one.
        </p>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <label className="field">
            <span className="field-label">Email</span>
            <input
              ref={emailRef}
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>

          <label className="field">
            <span className="field-label">Password</span>
            <input
              type="password"
              autoComplete="new-password"
              placeholder="At least 8 characters"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          {(localError ?? error) && <p className="field-error">{localError ?? error}</p>}

          <div className="modal-actions">
            <button type="button" className="button button-ghost" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="button button-primary" disabled={pending}>
              {pending ? <Spinner size={16} /> : 'Save account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
