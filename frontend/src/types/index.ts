export type Role = 'user' | 'assistant' | 'system'

/** Lifecycle of an assistant message as far as the UI is concerned. */
export type MessageStatus = 'complete' | 'streaming' | 'cancelled' | 'error'

export interface User {
  id: string
  /** null for guest accounts, which are identified by device_id instead. */
  email: string | null
  is_guest: boolean
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface Message {
  id: string
  conversation_id: string
  role: Role
  content: string
  created_at: string
  model?: string | null
  status?: MessageStatus
  /** Populated when status is 'error'. */
  error?: string | null
}

export interface Conversation extends ConversationSummary {
  messages: Message[]
}

/** Server-Sent Event payloads emitted while an assistant reply is generated. */
export type ChatStreamEvent =
  | { type: 'start'; conversation_id: string; message_id: string; model: string }
  | { type: 'delta'; text: string }
  | { type: 'done'; message_id: string; finish_reason?: string | null }
  | { type: 'error'; message: string }
