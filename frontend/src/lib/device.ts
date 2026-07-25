import { deviceStorage } from './storage'

/**
 * Stable per-browser identifier used to back guest sessions.
 *
 * This is deliberately *not* a fingerprint: it is a random UUID we generate and
 * store ourselves. That means it is not stable across browsers, profiles, or a
 * cleared storage, which is the correct tradeoff — a guest identity should be
 * disposable, and anything stronger would be tracking users who have not signed
 * in. If the id is lost, the guest simply gets a new empty account.
 */
export function getDeviceId(): string {
  const existing = deviceStorage.get()
  if (existing) return existing

  const id = generateUuid()
  deviceStorage.set(id)
  return id
}

export function resetDeviceId(): void {
  deviceStorage.clear()
}

function generateUuid(): string {
  // Available in all current browsers, but only over HTTPS/localhost.
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  // Fallback: RFC 4122 v4 assembled from getRandomValues.
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16)
    crypto.getRandomValues(bytes)
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }

  // Last resort for ancient/insecure contexts. Not cryptographically strong,
  // which is tolerable because this value only names a throwaway guest account.
  return `guest-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
