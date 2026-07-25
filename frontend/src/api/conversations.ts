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
export function getConversation(id: string, signal?: AbortSignal): Promise<Conversation> {
  return request<Conversation>(`/conversations/${encodeURIComponent(id)}`, { signal })
}

export function deleteConversation(id: string): Promise<void> {
  return request<void>(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function renameConversation(id: string, title: string): Promise<ConversationSummary> {
  return request<ConversationSummary>(`/conversations/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: { title },
  })
}
