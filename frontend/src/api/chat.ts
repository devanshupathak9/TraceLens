import { ApiError, apiUrl, authHeaders, request } from './client'
import { createSseParser } from '@/lib/sse'
import type { Message } from '@/types'

export interface SendMessageResult {
  user_message: Message
  assistant_message: Message
}

/**
 * One chat turn, non-streaming: resolves once the model reply is stored.
 * Kept for callers that want the whole turn in one piece.
 */
export function sendMessage(
  conversationId: number,
  content: string,
  signal?: AbortSignal,
): Promise<SendMessageResult> {
  return request<SendMessageResult>(`/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: { content },
    signal,
  })
}

/**
 * One chat turn, streamed. Calls `onDelta` per token and resolves with the
 * stored pair once the server sends its `done` frame.
 *
 * Uses raw fetch rather than the shared `request()` because it consumes an SSE
 * body and needs an AbortSignal for "stop generating"; EventSource can't send
 * the Authorization header, which is why the frames are parsed by hand.
 * Aborting surfaces as a DOMException named AbortError, which the caller treats
 * as a cancellation rather than a failure.
 */
export async function streamMessage(
  conversationId: number,
  content: string,
  onDelta: (text: string) => void,
  signal?: AbortSignal,
): Promise<SendMessageResult> {
  let response: Response
  try {
    response = await fetch(apiUrl(`/conversations/${conversationId}/messages/stream`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...authHeaders() },
      body: JSON.stringify({ content }),
      signal,
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError(0, 'Cannot reach the server. Check that the backend is running.', cause)
  }

  if (!response.ok || !response.body) {
    throw new ApiError(response.status, `Request failed (${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const parse = createSseParser()
  let result: SendMessageResult | null = null

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break

      for (const frame of parse(decoder.decode(value, { stream: true }))) {
        if (frame.event === 'delta') {
          onDelta((JSON.parse(frame.data) as { text: string }).text)
        } else if (frame.event === 'done') {
          result = JSON.parse(frame.data) as SendMessageResult
        } else if (frame.event === 'error') {
          throw new ApiError(502, (JSON.parse(frame.data) as { detail: string }).detail)
        }
      }
    }
  } finally {
    // Aborting mid-stream leaves the reader open; releasing it lets the browser
    // tear the connection down, which is what signals the backend to stop.
    reader.cancel().catch(() => {})
  }

  if (!result) throw new ApiError(0, 'The stream ended before the reply was saved.')
  return result
}
