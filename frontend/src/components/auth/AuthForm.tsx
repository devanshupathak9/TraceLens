import { useState, type FormEvent } from 'react'
import { useAuth } from '@/context/AuthContext'
import { Spinner } from '@/components/ui/Spinner'

const MIN_PASSWORD_LENGTH = 8

interface AuthFormProps {
  mode: 'login' | 'register'
}

export function AuthForm({ mode }: AuthFormProps) {
  const { login, register, pending } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  const isRegister = mode === 'register'

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setLocalError(null)

    // Client-side checks only catch the obvious cases; the backend remains the
    // authority on email uniqueness and password policy.
    if (!email.includes('@')) {
      setLocalError('Enter a valid email address.')
      return
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      setLocalError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }
    if (isRegister && password !== confirm) {
      setLocalError('Passwords do not match.')
      return
    }

    try {
      if (isRegister) await register(email, password)
      else await login(email, password)
    } catch {
      // Surfaced by the AuthContext banner.
    }
  }

  return (
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      <label className="field">
        <span className="field-label">Email</span>
        <input
          type="email"
          name="email"
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
          name="password"
          autoComplete={isRegister ? 'new-password' : 'current-password'}
          placeholder={isRegister ? `At least ${MIN_PASSWORD_LENGTH} characters` : '••••••••'}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
      </label>

      {isRegister && (
        <label className="field">
          <span className="field-label">Confirm password</span>
          <input
            type="password"
            name="confirmPassword"
            autoComplete="new-password"
            placeholder="Re-enter your password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            required
          />
        </label>
      )}

      {localError && <p className="field-error">{localError}</p>}

      <button type="submit" className="button button-primary button-block" disabled={pending}>
        {pending ? <Spinner size={16} /> : isRegister ? 'Create account' : 'Sign in'}
      </button>
    </form>
  )
}
