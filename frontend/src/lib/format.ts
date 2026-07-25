/** Groups conversations under Today / Yesterday / Previous 7 days / older. */
export function relativeGroup(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'Earlier'

  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)

  const days = Math.floor((startOfToday.getTime() - date.getTime()) / 86_400_000)

  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return 'Previous 7 days'
  if (days < 30) return 'Previous 30 days'

  return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

export function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

/** Derives a sidebar title from the first user message, mirroring ChatGPT. */
export function titleFromMessage(text: string, maxLength = 48): string {
  const cleaned = text.replace(/\s+/g, ' ').trim()
  if (!cleaned) return 'New chat'
  if (cleaned.length <= maxLength) return cleaned
  return `${cleaned.slice(0, maxLength - 1).trimEnd()}…`
}

export function initialsFor(user: { email: string | null; is_guest: boolean }): string {
  if (user.is_guest || !user.email) return 'G'
  return user.email.trim().charAt(0).toUpperCase() || '?'
}
