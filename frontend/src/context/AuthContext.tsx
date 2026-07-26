import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import * as authApi from '@/api/auth'
import { getAuthToken, setAuthToken, setUnauthorizedHandler } from '@/api/client'
import type { User } from '@/types'

interface AuthContextValue {
  user: User | null
  /** True until the stored token has been validated, so we don't flash the login screen. */
  initialising: boolean
  pending: boolean
  error: string | null
  register: (name: string, email: string, password: string) => Promise<void>
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  clearError: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [initialising, setInitialising] = useState(true)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Guards against a state update after unmount during the boot-time /users/me.
  // Set true in the effect body, not at declaration: StrictMode unmounts and
  // remounts once in dev, and the ref must recover from the first cleanup.
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  // Restore the session from the stored token on first load.
  useEffect(() => {
    if (!getAuthToken()) {
      setInitialising(false)
      return
    }

    authApi
      .me()
      .then((restored) => {
        if (mounted.current) setUser(restored)
      })
      .catch(() => {
        // Expired or tampered token — fall back to the sign-in screen.
        setAuthToken(null)
      })
      .finally(() => {
        if (mounted.current) setInitialising(false)
      })
  }, [])

  const logout = useCallback(() => {
    // Best-effort server call while the token is still set; the real logout is
    // the client forgetting the token.
    void authApi.logout().catch(() => {})
    setAuthToken(null)
    setUser(null)
    setError(null)
  }, [])

  // Any 401 from anywhere in the app ends the session.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null)
      setError('Your session expired. Please sign in again.')
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  /** Shared wrapper so every entry point gets identical pending/error handling. */
  const runAuth = useCallback(
    async (action: () => Promise<{ access_token: string; user: User }>) => {
      setPending(true)
      setError(null)
      try {
        const result = await action()
        setAuthToken(result.access_token)
        setUser(result.user)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Something went wrong.')
        throw cause
      } finally {
        if (mounted.current) setPending(false)
      }
    },
    [],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      initialising,
      pending,
      error,
      register: (name, email, password) => runAuth(() => authApi.register(name, email, password)),
      login: (email, password) => runAuth(() => authApi.login(email, password)),
      logout,
      clearError: () => setError(null),
    }),
    [user, initialising, pending, error, runAuth, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
