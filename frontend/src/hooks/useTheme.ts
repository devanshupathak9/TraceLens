import { useCallback, useEffect, useState } from 'react'
import { themeStorage, type Theme } from '@/lib/storage'

/**
 * Light/dark theme with an explicit override.
 *
 * With nothing stored we follow the OS preference via CSS `prefers-color-scheme`
 * and leave `data-theme` off the root element entirely; toggling sets the
 * attribute, which the stylesheet gives higher precedence than the media query.
 */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => themeStorage.get() ?? systemTheme())

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  // Track the OS preference until the user makes an explicit choice.
  useEffect(() => {
    if (themeStorage.get()) return

    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (event: MediaQueryListEvent) => {
      if (!themeStorage.get()) setTheme(event.matches ? 'dark' : 'light')
    }

    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === 'dark' ? 'light' : 'dark'
      themeStorage.set(next)
      return next
    })
  }, [])

  return { theme, toggleTheme }
}

function systemTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}
