/**
 * Thin, failure-tolerant wrapper around localStorage.
 *
 * Safari in private mode and some embedded webviews throw on access rather than
 * returning null, so every call is guarded. Losing persistence degrades the app
 * to "signed out on reload", which is acceptable; crashing is not.
 */

const TOKEN_KEY = 'chatjippity.token'
const THEME_KEY = 'chatjippity.theme'

export type Theme = 'light' | 'dark'

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* storage unavailable — session becomes in-memory only */
  }
}

function remove(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* nothing to do */
  }
}

export const tokenStorage = {
  get: () => read(TOKEN_KEY),
  set: (token: string) => write(TOKEN_KEY, token),
  clear: () => remove(TOKEN_KEY),
}

export const themeStorage = {
  get: (): Theme | null => {
    const value = read(THEME_KEY)
    return value === 'light' || value === 'dark' ? value : null
  },
  set: (theme: Theme) => write(THEME_KEY, theme),
}
