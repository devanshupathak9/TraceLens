import { useCallback, useEffect, useRef, useState } from 'react'

const NEAR_BOTTOM_PX = 120

/**
 * Keeps a scroll container pinned to the newest content while tokens stream in,
 * but yields control the moment the user scrolls up to read earlier output —
 * fighting the user's scroll position is the classic chat-UI bug.
 */
export function useAutoScroll<T>(dependency: T) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const pinnedRef = useRef(true)
  const [showJumpButton, setShowJumpButton] = useState(false)

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const node = containerRef.current
    if (!node) return
    node.scrollTo({ top: node.scrollHeight, behavior })
    pinnedRef.current = true
    setShowJumpButton(false)
  }, [])

  const handleScroll = useCallback(() => {
    const node = containerRef.current
    if (!node) return

    const distance = node.scrollHeight - node.scrollTop - node.clientHeight
    const pinned = distance <= NEAR_BOTTOM_PX
    pinnedRef.current = pinned
    setShowJumpButton(!pinned)
  }, [])

  useEffect(() => {
    if (pinnedRef.current) {
      // 'auto' rather than 'smooth': during streaming a smooth animation restarts
      // on every token and the view never actually reaches the bottom.
      containerRef.current?.scrollTo({ top: containerRef.current.scrollHeight, behavior: 'auto' })
    }
  }, [dependency])

  return { containerRef, handleScroll, scrollToBottom, showJumpButton }
}
