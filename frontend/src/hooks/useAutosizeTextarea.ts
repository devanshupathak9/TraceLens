import { useEffect, useRef } from 'react'

/**
 * Grows a textarea with its content up to `maxHeight`, then scrolls internally.
 * Height is reset to 'auto' before measuring so the element can shrink again
 * when text is deleted.
 */
export function useAutosizeTextarea(value: string, maxHeight = 200) {
  const ref = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    node.style.height = 'auto'
    const next = Math.min(node.scrollHeight, maxHeight)
    node.style.height = `${next}px`
    node.style.overflowY = node.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [value, maxHeight])

  return ref
}
