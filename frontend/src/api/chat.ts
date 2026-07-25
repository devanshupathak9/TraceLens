import { ApiError, apiUrl, authHeaders } from './client'
import { readSseStream } from '@/lib/sse'
import type { ChatStreamEvent } from '@/types'

export interface SendMessageOptions {
  conversationId: string
  content: string
  signal: AbortSignal
  onEvent: (event: ChatStreamEvent) => void
}

/**
 * Posts a user message and consumes the streamed assistant reply.
 *
 * Resolves once the stream closes cleanly. Aborting via `signal` surfaces as a
 * DOMException named AbortError, which the caller treats as a user cancellation
 * rather than a failure.
 */
export async function sendMessage({
  conversationId,
  content,
  signal,
  onEvent,
}: SendMessageOptions): Promise<void> {
  let response: Response
  try {
    response = await fetch(apiUrl(`/conversations/${encodeURIComponent(conversationId)}/messages`), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...authHeaders(),
      },
      body: JSON.stringify({ content }),
      signal,
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError(0, 'Cannot reach the server. Check that the backend is running.', cause)
  }

  if (!response.ok) {
    // Failures before the stream opens come back as ordinary JSON.
    let message = `Request failed (${response.status})`
    try {
      const payload = (await response.json()) as { detail?: unknown }
      if (typeof payload.detail === 'string') message = payload.detail
    } catch {
      /* keep the status-based fallback */
    }
    throw new ApiError(response.status, message)
  }

  if (!response.body) {
    throw new ApiError(0, 'The server returned an empty response stream.')
  }

  for await (const frame of readSseStream(response.body)) {
    const event = toStreamEvent(frame.event, frame.data)
    if (event) onEvent(event)
  }
}

/**
 * Normalises a raw frame into a typed event.
 *
 * The event name is trusted when present, but the payload's own `type` field
 * wins if the two disagree — that keeps the client working whether the backend
 * uses named events or a single `message` event carrying a discriminator.
 */
function toStreamEvent(eventName: string, data: string): ChatStreamEvent | null {
  // Some SSE producers send a literal [DONE] sentinel instead of a JSON frame.
  if (data === '[DONE]') return null

  let payload: Record<string, unknown>
  try {
    payload = JSON.parse(data) as Record<string, unknown>
  } catch {
    // A non-JSON frame is treated as a raw token so output is never lost.
    return eventName === 'delta' || eventName === 'message'
      ? { type: 'delta', text: data }
      : null
  }

  const type = typeof payload.type === 'string' ? payload.type : eventName

  switch (type) {
    case 'start':
      return {
        type: 'start',
        conversation_id: String(payload.conversation_id ?? ''),
        message_id: String(payload.message_id ?? ''),
        model: String(payload.model ?? ''),
      }
    case 'delta':
    case 'token':
    case 'message': {
      const text = payload.text ?? payload.delta ?? payload.content
      return typeof text === 'string' ? { type: 'delta', text } : null
    }
    case 'done':
      return {
        type: 'done',
        message_id: String(payload.message_id ?? ''),
        finish_reason: typeof payload.finish_reason === 'string' ? payload.finish_reason : null,
      }
    case 'error':
      return {
        type: 'error',
        message:
          typeof payload.message === 'string'
            ? payload.message
            : 'The model failed to generate a reply.',
      }
    default:
      return null
  }
}
