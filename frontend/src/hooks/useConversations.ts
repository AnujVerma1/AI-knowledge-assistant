import { useCallback, useEffect, useState } from 'react'
import { api, describeError } from '../services/api'
import type { Conversation } from '../types/api'

export function useConversations() {
  const [items, setItems] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const response = await api.conversations.list()
      setItems(response.conversations)
      setError(null)
    } catch (e) {
      setError(describeError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const remove = useCallback(async (id: string) => {
    await api.conversations.remove(id)
    setItems((previous) => previous.filter((c) => c.id !== id))
  }, [])

  return { items, loading, error, refresh, remove }
}

export type ConversationsState = ReturnType<typeof useConversations>

/** Shared with pages through the layout's <Outlet context>. */
export interface LayoutContext {
  conversations: ConversationsState
}
