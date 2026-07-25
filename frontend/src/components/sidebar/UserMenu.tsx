import { useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { UpgradeGuestDialog } from '@/components/auth/UpgradeGuestDialog'
import { LogoutIcon, MoonIcon, SunIcon } from '@/components/ui/Icons'
import { initialsFor } from '@/lib/format'
import type { Theme } from '@/lib/storage'

interface UserMenuProps {
  theme: Theme
  onToggleTheme: () => void
}

export function UserMenu({ theme, onToggleTheme }: UserMenuProps) {
  const { user, logout } = useAuth()
  const [upgrading, setUpgrading] = useState(false)

  if (!user) return null

  return (
    <div className="user-menu">
      {user.is_guest && (
        <button type="button" className="upgrade-prompt" onClick={() => setUpgrading(true)}>
          Save your chats →
        </button>
      )}

      <div className="user-row">
        <span className="avatar" aria-hidden="true">
          {initialsFor(user)}
        </span>

        <span className="user-identity">
          <span className="user-name">{user.email ?? 'Guest'}</span>
          <span className="user-sub">{user.is_guest ? 'This browser only' : 'Signed in'}</span>
        </span>

        <button
          type="button"
          className="icon-button"
          onClick={onToggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          title={theme === 'dark' ? 'Light theme' : 'Dark theme'}
        >
          {theme === 'dark' ? <SunIcon width={16} height={16} /> : <MoonIcon width={16} height={16} />}
        </button>

        <button
          type="button"
          className="icon-button"
          onClick={logout}
          aria-label="Sign out"
          title="Sign out"
        >
          <LogoutIcon width={16} height={16} />
        </button>
      </div>

      {upgrading && <UpgradeGuestDialog onClose={() => setUpgrading(false)} />}
    </div>
  )
}
