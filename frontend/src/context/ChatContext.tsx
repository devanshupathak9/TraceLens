import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import * as conversationsApi from '@/api/conversations'
import { sendMessage as streamMessage } from '@/api/chat'
import { titleFromMessage } from '@/lib/format'
import { useAuth } from './AuthContext'
import type { ConversationSummary, Message } from '@/types'

interface ChatContextValue {
  conversations: ConversationSummary[]
  activeId: string | null
  messages: Message[]
  loadingList: boolean
  loadingMessages: boolean
  streaming: boolean
  error: string | null
  startNewChat: () => void
  selectConversation: (id: string) => void
  submitMessage: (content: string) => Promise<void>
  cancelStreaming: () => void
  removeConversation: (id: string) => Promise<void>
  renameConversation: (id: string, title: string) => Promise<void>
  dismissError: () => void
}

const ChatContext = createContext<ChatContextValue | null>(null)

function isAbort(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'AbortError'
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loadingList, setLoadingList] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /** Aborts the in-flight generation when the user hits stop or switches away. */
  const streamAbort = useRef<AbortController | null>(null)
  /** Aborts a history fetch that has been superseded by a newer selection. */
  const loadAbort = useRef<AbortController | null>(null)
  /**
   * Monotonic token identifying the newest history load. Responses carrying an
   * older token are discarded, so quickly clicking through the sidebar can't
   * leave the wrong messages on screen.
   */
  const loadToken = useRef(0)

  const resetState = useCallback(() => {
    streamAbort.current?.abort()
    loadAbort.current?.abort()
    streamAbort.current = null
    loadAbort.current = null
    setConversations([])
    setMessages([])
    setActiveId(null)
    setStreaming(false)
    setError(null)
  }, [])

  // Load the sidebar whenever the signed-in user changes, and clear everything on
  // sign-out so one account's history is never visible to the next.
  useEffect(() => {
    if (!user) {
      resetState()
      return
    }

    const controller = new AbortController()
    setLoadingList(true)

    conversationsApi
      .listConversations(controller.signal)
      .then(setConversations)
      .catch((cause) => {
        if (!isAbort(cause)) {
          setError(cause instanceof Error ? cause.message : 'Could not load conversations.')
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingList(false)
      })

    return () => controller.abort()
  }, [user, resetState])

  const startNewChat = useCallback(() => {
    // The conversation row is created lazily on first send, so an abandoned
    // "New chat" never leaves an empty record behind.
    streamAbort.current?.abort()
    loadAbort.current?.abort()
    loadToken.current += 1
    setActiveId(null)
    setMessages([])
    setError(null)
  }, [])

  const selectConversation = useCallback(
    (id: string) => {
      if (id === activeId) return

      streamAbort.current?.abort()
      loadAbort.current?.abort()

      const controller = new AbortController()
      loadAbort.current = controller
      const token = (loadToken.current += 1)

      setActiveId(id)
      setMessages([])
      setError(null)
      setLoadingMessages(true)

      conversationsApi
        .getConversation(id, controller.signal)
        .then((conversation) => {
          if (loadToken.current !== token) return
          setMessages(conversation.messages)
          // Keep the sidebar row in sync with whatever the server just told us.
          setConversations((current) =>
            current.map((item) =>
              item.id === conversation.id
                ? {
                    ...item,
                    title: conversation.title,
                    updated_at: conversation.updated_at,
                    message_count: conversation.messages.length,
                  }
                : item,
            ),
          )
        })
        .catch((cause) => {
          if (isAbort(cause) || loadToken.current !== token) return
          setError(cause instanceof Error ? cause.message : 'Could not open that conversation.')
        })
        .finally(() => {
          if (loadToken.current === token) setLoadingMessages(false)
        })
    },
    [activeId],
  )

  const cancelStreaming = useCallback(() => {
    streamAbort.current?.abort()
  }, [])

  /** Rewrites the assistant placeholder in place as tokens arrive. */
  const patchMessage = useCallback((id: string, patch: Partial<Message>) => {
    setMessages((current) =>
      current.map((message) => (message.id === id ? { ...message, ...patch } : message)),
    )
  }, [])

  const submitMessage = useCallback(
    async (content: string) => {
      const trimmed = content.trim()
      if (!trimmed || streaming) return

      setError(null)

      // Create the conversation on demand if this is a fresh chat.
      let conversationId = activeId
      let createdConversation: ConversationSummary | null = null

      if (!conversationId) {
        try {
          createdConversation = await conversationsApi.createConversation(
            titleFromMessage(trimmed),
          )
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : 'Could not start a conversation.')
          return
        }
        conversationId = createdConversation.id
        setConversations((current) => [createdConversation as ConversationSummary, ...current])
        setActiveId(conversationId)
      }

      const now = new Date().toISOString()
      const userMessage: Message = {
        id: `local-user-${now}-${Math.random().toString(36).slice(2, 8)}`,
        conversation_id: conversationId,
        role: 'user',
        content: trimmed,
        created_at: now,
        status: 'complete',
      }
      const placeholderId = `local-assistant-${now}-${Math.random().toString(36).slice(2, 8)}`
      const placeholder: Message = {
        id: placeholderId,
        conversation_id: conversationId,
        role: 'assistant',
        content: '',
        created_at: now,
        status: 'streaming',
      }

      setMessages((current) => [...current, userMessage, placeholder])

      const controller = new AbortController()
      streamAbort.current = controller
      setStreaming(true)

      // Accumulated locally: appending to a ref avoids a re-render race where two
      // deltas arriving in the same tick would both read the same stale state.
      let accumulated = ''
      let serverMessageId: string | null = null

      try {
        await streamMessage({
          conversationId,
          content: trimmed,
          signal: controller.signal,
          onEvent: (event) => {
            switch (event.type) {
              case 'start':
                serverMessageId = event.message_id || null
                patchMessage(placeholderId, { model: event.model || null })
                break
              case 'delta':
                accumulated += event.text
                patchMessage(placeholderId, { content: accumulated })
                break
              case 'done':
                patchMessage(placeholderId, {
                  id: event.message_id || serverMessageId || placeholderId,
                  content: accumulated,
                  status: 'complete',
                })
                break
              case 'error':
                patchMessage(placeholderId, {
                  content: accumulated,
                  status: 'error',
                  error: event.message,
                })
                break
            }
          },
        })

        // Defensive: if the server closed without an explicit done frame, don't
        // leave the bubble stuck in a streaming state forever.
        setMessages((current) =>
          current.map((message) =>
            message.id === placeholderId && message.status === 'streaming'
              ? { ...message, status: 'complete' }
              : message,
          ),
        )
      } catch (cause) {
        if (isAbort(cause)) {
          // Partial output is kept — it's still the model's answer, just truncated.
          patchMessage(placeholderId, { content: accumulated, status: 'cancelled' })
        } else {
          const message = cause instanceof Error ? cause.message : 'The request failed.'
          patchMessage(placeholderId, { content: accumulated, status: 'error', error: message })
          setError(message)
        }
      } finally {
        streamAbort.current = null
        setStreaming(false)

        // Bump the conversation so it sorts to the top of the sidebar, matching
        // where the server will place it on the next fetch.
        const finishedAt = new Date().toISOString()
        setConversations((current) => {
          const updated = current.map((item) =>
            item.id === conversationId
              ? { ...item, updated_at: finishedAt, message_count: item.message_count + 2 }
              : item,
          )
          return [...updated].sort(
            (a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at),
          )
        })
      }
    },
    [activeId, streaming, patchMessage],
  )

  const removeConversation = useCallback(
    async (id: string) => {
      // Snapshot for rollback: the row is removed immediately so the UI feels
      // instant, then restored if the server rejects the delete.
      const snapshot = conversations
      setConversations((current) => current.filter((item) => item.id !== id))

      if (id === activeId) {
        streamAbort.current?.abort()
        setActiveId(null)
        setMessages([])
      }

      try {
        await conversationsApi.deleteConversation(id)
      } catch (cause) {
        setConversations(snapshot)
        setError(cause instanceof Error ? cause.message : 'Could not delete that conversation.')
      }
    },
    [conversations, activeId],
  )

  const renameConversation = useCallback(
    async (id: string, title: string) => {
      const trimmed = title.trim()
      if (!trimmed) return

      const snapshot = conversations
      setConversations((current) =>
        current.map((item) => (item.id === id ? { ...item, title: trimmed } : item)),
      )

      try {
        await conversationsApi.renameConversation(id, trimmed)
      } catch (cause) {
        setConversations(snapshot)
        setError(cause instanceof Error ? cause.message : 'Could not rename that conversation.')
      }
    },
    [conversations],
  )

  const value = useMemo<ChatContextValue>(
    () => ({
      conversations,
      activeId,
      messages,
      loadingList,
      loadingMessages,
      streaming,
      error,
      startNewChat,
      selectConversation,
      submitMessage,
      cancelStreaming,
      removeConversation,
      renameConversation,
      dismissError: () => setError(null),
    }),
    [
      conversations,
      activeId,
      messages,
      loadingList,
      loadingMessages,
      streaming,
      error,
      startNewChat,
      selectConversation,
      submitMessage,
      cancelStreaming,
      removeConversation,
      renameConversation,
    ],
  )

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export function useChat(): ChatContextValue {
  const context = useContext(ChatContext)
  if (!context) throw new Error('useChat must be used inside <ChatProvider>')
  return context
}
