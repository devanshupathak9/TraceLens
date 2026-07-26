import { request } from './client'
import type { Message } from '@/types'

export interface SendMessageResult {
  user_message: Message
  assistant_message: Message
}

/**
 * One chat turn: posts the user message and resolves once the model reply is
 * stored. Non-streaming — the backend returns both messages as plain JSON.
 * Aborting via `signal` surfaces as a DOMException named AbortError, which the
 * caller treats as a user cancellation rather than a failure.
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
