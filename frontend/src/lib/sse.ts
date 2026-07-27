/**
 * Minimal SSE frame parser.
 *
 * The browser's EventSource can't send an Authorization header, so the stream is
 * consumed with fetch() and parsed by hand. Frames are separated by a blank
 * line; a frame may carry an `event:` name and one or more `data:` lines, which
 * concatenate with newlines. Lines starting with `:` are keepalive comments.
 */
export interface SseFrame {
  event: string
  data: string
}

export function createSseParser() {
  let buffer = ''

  /** Feeds a chunk in and returns whatever complete frames it produced. */
  return function push(chunk: string): SseFrame[] {
    buffer += chunk
    const frames: SseFrame[] = []

    // Normalise CRLF so the split below doesn't leave stray \r on values.
    buffer = buffer.replace(/\r\n/g, '\n')

    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)

      let event = 'message'
      const dataLines: string[] = []
      for (const line of raw.split('\n')) {
        if (!line || line.startsWith(':')) continue
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      }
      if (dataLines.length > 0) frames.push({ event, data: dataLines.join('\n') })

      boundary = buffer.indexOf('\n\n')
    }

    return frames
  }
}
