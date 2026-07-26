import { tokenStorage } from '@/lib/storage'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly detail?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * The bearer token lives in this module rather than in React state so that
 * `request()` stays callable from anywhere without threading it through every
 * call site — and so api modules don't have to import the auth context, which
 * would be a cycle.
 */
let authToken: string | null = tokenStorage.get()

export function setAuthToken(token: string | null): void {
  authToken = token
  if (token) tokenStorage.set(token)
  else tokenStorage.clear()
}

export function getAuthToken(): string | null {
  return authToken
}

/**
 * Registered by AuthContext so an expired token anywhere in the app drops the
 * user back to the sign-in screen instead of surfacing a wall of 401s.
 */
type UnauthorizedHandler = () => void
let onUnauthorized: UnauthorizedHandler | null = null

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler
}

export function authHeaders(): Record<string, string> {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {}
}

export function apiUrl(path: string): string {
  return `${BASE_URL}${path}`
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  signal?: AbortSignal
  /** Set for endpoints that must not trigger a global sign-out on 401. */
  skipAuthRedirect?: boolean
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, skipAuthRedirect = false } = options

  const headers: Record<string, string> = { Accept: 'application/json', ...authHeaders() }
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(apiUrl(path), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError(0, 'Cannot reach the server. Check that the backend is running.', cause)
  }

  if (response.status === 401 && !skipAuthRedirect) {
    setAuthToken(null)
    onUnauthorized?.()
  }

  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }

  if (response.status === 204) return undefined as T

  const text = await response.text()
  if (!text) return undefined as T
  return JSON.parse(text) as T
}

/** FastAPI reports errors as `detail`, which may be a string or a list of issues. */
async function errorMessage(response: Response): Promise<string> {
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    return `Request failed (${response.status})`
  }

  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) =>
          item && typeof item === 'object' && 'msg' in item
            ? String((item as { msg: unknown }).msg)
            : null,
        )
        .filter((msg): msg is string => Boolean(msg))
      if (messages.length) return messages.join('. ')
    }
  }

  return `Request failed (${response.status})`
}
