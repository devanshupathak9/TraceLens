import { useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { AuthForm } from './AuthForm'
import { Banner } from '@/components/ui/Banner'
import { SparkIcon } from '@/components/ui/Icons'

type Mode = 'login' | 'register'

export function AuthScreen() {
  const { error, clearError } = useAuth()
  const [mode, setMode] = useState<Mode>('login')

  const switchMode = (next: Mode) => {
    clearError()
    setMode(next)
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-logo">
            <SparkIcon width={22} height={22} />
          </span>
          <h1>ChatJippity</h1>
          <p className="auth-tagline">
            {mode === 'login' ? 'Sign in to continue your chats.' : 'Create an account to save your chats.'}
          </p>
        </div>

        <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'login'}
            className={mode === 'login' ? 'auth-tab active' : 'auth-tab'}
            onClick={() => switchMode('login')}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'register'}
            className={mode === 'register' ? 'auth-tab active' : 'auth-tab'}
            onClick={() => switchMode('register')}
          >
            Register
          </button>
        </div>

        {error && <Banner message={error} onDismiss={clearError} />}

        <AuthForm mode={mode} />
      </div>
    </div>
  )
}
