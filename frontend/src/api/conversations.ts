import { request } from './client'
import type { Conversation, ConversationSummary } from '@/types'

export function listConversations(signal?: AbortSignal): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>('/conversations', { signal })
}

export function createConversation(title?: string): Promise<ConversationSummary> {
  return request<ConversationSummary>('/conversations', {
    method: 'POST',
    body: title === undefined ? {} : { title },
  })
}

/** Returns the conversation with its full message history. */
export function getConversation(id: number, signal?: AbortSignal): Promise<Conversation> {
  return request<Conversation>(`/conversations/${id}`, { signal })
}

export function deleteConversation(id: number): Promise<void> {
  return request<void>(`/conversations/${id}`, { method: 'DELETE' })
}

export function renameConversation(id: number, title: string): Promise<ConversationSummary> {
  return request<ConversationSummary>(`/conversations/${id}`, {
    method: 'PATCH',
    body: { title },
  })
}
