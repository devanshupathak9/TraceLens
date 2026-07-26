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
import * as chatApi from '@/api/chat'
import { titleFromMessage } from '@/lib/format'
import { useAuth } from './AuthContext'
import type { ConversationSummary, Message } from '@/types'

interface ChatContextValue {
  conversations: ConversationSummary[]
  activeId: number | null
  messages: Message[]
  loadingList: boolean
  loadingMessages: boolean
  /** True while a chat turn is in flight — the reply arrives in one piece. */
  streaming: boolean
  error: string | null
  startNewChat: () => void
  selectConversation: (id: number) => void
  submitMessage: (content: string) => Promise<void>
  cancelStreaming: () => void
  removeConversation: (id: number) => Promise<void>
  renameConversation: (id: number, title: string) => Promise<void>
  dismissError: () => void
}

const ChatContext = createContext<ChatContextValue | null>(null)

function isAbort(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'AbortError'
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loadingList, setLoadingList] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /** Aborts the in-flight chat turn when the user hits stop or switches away. */
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
    (id: number) => {
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
                    last_active_at: conversation.last_active_at,
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

  const patchMessage = useCallback((id: Message['id'], patch: Partial<Message>) => {
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
      if (conversationId === null) {
        try {
          const created = await conversationsApi.createConversation(titleFromMessage(trimmed))
          conversationId = created.id
          setConversations((current) => [created, ...current])
          setActiveId(conversationId)
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : 'Could not start a conversation.')
          return
        }
      }

      // Optimistic pair: the user's message plus an assistant placeholder that
      // shows a typing indicator until the server returns the stored turn.
      const now = new Date().toISOString()
      const localUserId = `local-user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const placeholderId = `local-assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

      setMessages((current) => [
        ...current,
        {
          id: localUserId,
          conversation_id: conversationId,
          role: 'user',
          content: trimmed,
          created_at: now,
          status: 'complete',
        },
        {
          id: placeholderId,
          conversation_id: conversationId,
          role: 'assistant',
          content: '',
          created_at: now,
          status: 'streaming',
        },
      ])

      const controller = new AbortController()
      streamAbort.current = controller
      setStreaming(true)

      try {
        const result = await chatApi.sendMessage(conversationId, trimmed, controller.signal)
        // Swap both optimistic messages for the server's stored versions.
        setMessages((current) =>
          current.map((message) => {
            if (message.id === localUserId) return { ...result.user_message, status: 'complete' as const }
            if (message.id === placeholderId) return { ...result.assistant_message, status: 'complete' as const }
            return message
          }),
        )
      } catch (cause) {
        if (isAbort(cause)) {
          // Cancelled client-side. The server may still finish and store the
          // turn — reopening the conversation shows whatever it kept.
          setMessages((current) => current.filter((message) => message.id !== placeholderId))
        } else {
          const message = cause instanceof Error ? cause.message : 'The request failed.'
          patchMessage(placeholderId, { status: 'error', error: message })
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
              ? { ...item, last_active_at: finishedAt, message_count: item.message_count + 2 }
              : item,
          )
          return [...updated].sort(
            (a, b) => Date.parse(b.last_active_at) - Date.parse(a.last_active_at),
          )
        })
      }
    },
    [activeId, streaming, patchMessage],
  )

  const removeConversation = useCallback(
    async (id: number) => {
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
    async (id: number, title: string) => {
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
