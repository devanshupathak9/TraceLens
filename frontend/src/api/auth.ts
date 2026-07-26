import { request } from './client'
import type { AuthResponse, User } from '@/types'

export function register(name: string, email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>('/users/register', {
    method: 'POST',
    body: { name, email, password },
    skipAuthRedirect: true,
  })
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>('/users/login', {
    method: 'POST',
    body: { email, password },
    skipAuthRedirect: true,
  })
}

/** Validates a stored token on boot and returns the current user. */
export function me(): Promise<User> {
  return request<User>('/users/me', { skipAuthRedirect: true })
}

/** JWTs are stateless — this is a courtesy call; the client forgetting the token is the real logout. */
export function logout(): Promise<void> {
  return request<{ status: string }>('/users/logout', {
    method: 'POST',
    skipAuthRedirect: true,
  }).then(() => undefined)
}
