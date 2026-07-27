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

export interface ModelUsage {
  model: string
  calls: number
  avg_latency_ms: number
  prompt_tokens: number
  completion_tokens: number
  /** null when the server has no price on file for this model. */
  cost_usd: number | null
}

export interface ThroughputPoint {
  /** Start of the hour bucket, ISO 8601. */
  bucket: string
  calls: number
  failed: number
}

export interface DashboardStats {
  total_calls: number
  success_calls: number
  failed_calls: number
  avg_latency_ms: number
  total_prompt_tokens: number
  total_completion_tokens: number
  total_tokens: number
  /** Sum over priced models only — see `unpriced_models`. */
  total_cost_usd: number
  /** Models with no price on file, so the total can be shown as a floor. */
  unpriced_models: string[]
  models: ModelUsage[]
  throughput: ThroughputPoint[]
}
