/**
 * Minimal Server-Sent Events reader.
 *
 * The browser's built-in EventSource only issues GET requests and cannot send an
 * Authorization header, so sending a chat message has to use fetch + a manual
 * frame parser. Doing it by hand also gives us an AbortSignal, which is what
 * makes "stop generating" work.
 */

export interface SseFrame {
  event: string
  data: string
}

/**
 * Splits a byte stream into SSE frames.
 *
 * Frames are separated by a blank line. A frame may carry several `data:` lines,
 * which the spec says to join with newlines — that matters because model output
 * legitimately contains newlines.
 */
export async function* readSseStream(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<SseFrame> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      for (;;) {
        const boundary = findBoundary(buffer)
        if (!boundary) break

        const raw = buffer.slice(0, boundary.index)
        buffer = buffer.slice(boundary.index + boundary.length)

        const frame = parseFrame(raw)
        if (frame) yield frame
      }
    }

    // A well-behaved server ends with a blank line, but flush anything left so a
    // final frame isn't silently dropped on an abrupt close.
    buffer += decoder.decode()
    const trailing = parseFrame(buffer)
    if (trailing) yield trailing
  } finally {
    reader.releaseLock()
  }
}

/** Locates the first blank-line frame separator, tolerating CRLF. */
function findBoundary(buffer: string): { index: number; length: number } | null {
  const lf = buffer.indexOf('\n\n')
  const crlf = buffer.indexOf('\r\n\r\n')

  if (lf === -1 && crlf === -1) return null
  if (crlf !== -1 && (lf === -1 || crlf < lf)) return { index: crlf, length: 4 }
  return { index: lf, length: 2 }
}

function parseFrame(raw: string): SseFrame | null {
  if (!raw.trim()) return null

  let event = 'message'
  const dataLines: string[] = []

  for (const line of raw.split(/\r?\n/)) {
    // Lines beginning with a colon are comments; servers use them as keepalives.
    if (!line || line.startsWith(':')) continue

    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)

    // Exactly one leading space after the colon is part of the framing.
    if (value.startsWith(' ')) value = value.slice(1)

    if (field === 'event') event = value
    else if (field === 'data') dataLines.push(value)
  }

  if (dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}
