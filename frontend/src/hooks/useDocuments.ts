import { useCallback, useEffect, useState } from 'react'
import { api, describeError } from '../services/api'
import type { DocumentItem } from '../types/api'

const POLL_INTERVAL_MS = 2500

/** The user's documents. While any document is processing, the list refreshes itself. */
export function useDocuments({ poll = true }: { poll?: boolean } = {}) {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const response = await api.documents.list()
      setDocuments(response.documents)
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

  const hasProcessing = documents.some((d) => d.status === 'processing')
  useEffect(() => {
    if (!poll || !hasProcessing) return
    const timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [poll, hasProcessing, refresh])

  return { documents, setDocuments, loading, error, refresh }
}
