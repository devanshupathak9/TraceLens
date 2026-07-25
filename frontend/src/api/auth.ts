import { request } from './client'
import type { AuthResponse, User } from '@/types'

export function register(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/register', {
    method: 'POST',
    body: { email, password },
    skipAuthRedirect: true,
  })
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/login', {
    method: 'POST',
    body: { email, password },
    skipAuthRedirect: true,
  })
}

/**
 * Exchanges a device id for a guest session. The backend is expected to be
 * idempotent here: the same device id returns the same guest account, so a
 * returning guest keeps their conversation history.
 */
export function loginAsGuest(deviceId: string): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/guest', {
    method: 'POST',
    body: { device_id: deviceId },
    skipAuthRedirect: true,
  })
}

/** Validates a stored token on boot and returns the current user. */
export function me(): Promise<User> {
  return request<User>('/auth/me', { skipAuthRedirect: true })
}

/**
 * Upgrades the signed-in guest to a permanent account, keeping their existing
 * conversations attached to the same user row.
 */
export function upgradeGuest(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/upgrade', {
    method: 'POST',
    body: { email, password },
  })
}
