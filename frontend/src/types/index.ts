export type Role = 'user' | 'assistant'

/** Lifecycle of an assistant message as far as the UI is concerned. */
export type MessageStatus = 'complete' | 'streaming' | 'cancelled' | 'error'

export interface User {
  id: number
  name: string
  email: string
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export interface ConversationSummary {
  id: number
  title: string
  model: string
  created_at: string
  last_active_at: string
  message_count: number
}

export interface Message {
  /** Server ids are numbers; optimistic local messages use string ids until reconciled. */
  id: number | string
  conversation_id: number
  role: Role
  content: string
  created_at: string
  status?: MessageStatus
  /** Populated when status is 'error'. */
  error?: string | null
}

export interface Conversation extends ConversationSummary {
  messages: Message[]
}
