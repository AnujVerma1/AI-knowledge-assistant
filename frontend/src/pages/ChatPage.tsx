import { FileUp, MessageSquareText } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useOutletContext, useParams } from 'react-router'
import { CitationPanel } from '../components/CitationPanel'
import { Composer, MAX_QUESTION_LENGTH } from '../components/Composer'
import { ErrorBanner } from '../components/ErrorBanner'
import { MessageItem, ThinkingIndicator } from '../components/MessageItem'
import { Spinner } from '../components/Spinner'
import type { LayoutContext } from '../hooks/useConversations'
import { useDocuments } from '../hooks/useDocuments'
import { api, describeError } from '../services/api'
import type { Citation, Message } from '../types/api'

export function ChatPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const { conversations } = useOutletContext<LayoutContext>()
  const { documents, loading: documentsLoading } = useDocuments({ poll: false })
  const readyCount = documents.filter((d) => d.status === 'ready').length

  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [panel, setPanel] = useState<{ citations: Citation[]; focus?: string } | null>(null)
  // Set when this page itself moves from /chat to /chat/:id and already has the messages.
  const skipNextLoad = useRef(false)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (skipNextLoad.current) {
      skipNextLoad.current = false
      return
    }
    setPanel(null)
    setSendError(null)
    setLoadError(null)
    if (!conversationId) {
      setMessages([])
      return
    }
    let cancelled = false
    setLoading(true)
    api.conversations
      .get(conversationId)
      .then((conversation) => !cancelled && setMessages(conversation.messages))
      .catch((e) => !cancelled && setLoadError(describeError(e)))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [conversationId])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, sending])

  async function send() {
    const question = draft.trim()
    if (!question || sending) return
    setSending(true)
    setSendError(null)
    setDraft('')
    const pending: Message = { id: 'pending', role: 'user', content: question, citations: null, created_at: new Date().toISOString() }
    setMessages((previous) => [...previous, pending])

    let id = conversationId
    try {
      id ??= (await api.conversations.create()).id
      const response = await api.conversations.ask(id, question)
      setMessages((previous) => [...previous.filter((m) => m.id !== 'pending'), response.user_message, response.assistant_message])
      // On wide screens show the sources next to the answer; on phones the panel would cover it.
      const citations = response.assistant_message.citations
      if (citations?.length && window.matchMedia('(min-width: 1024px)').matches) setPanel({ citations })
    } catch (e) {
      // Nothing was saved on the server, so restore the question for another try.
      setMessages((previous) => previous.filter((m) => m.id !== 'pending'))
      setDraft(question)
      setSendError(describeError(e))
    } finally {
      setSending(false)
      if (id && id !== conversationId) {
        skipNextLoad.current = true
        navigate(`/chat/${id}`, { replace: true })
      }
      void conversations.refresh()
    }
  }

  const noDocuments = !documentsLoading && readyCount === 0

  return (
    <div className="flex h-full">
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
            {loadError && <ErrorBanner message={loadError} />}
            {loading ? (
              <div className="flex justify-center py-16 text-zinc-400">
                <Spinner className="size-5" />
              </div>
            ) : messages.length === 0 && !loadError ? (
              <EmptyChat noDocuments={noDocuments} readyCount={readyCount} />
            ) : (
              messages.map((m) => <MessageItem key={m.id} message={m} onOpenCitations={(citations, focus) => setPanel({ citations, focus })} />)
            )}
            {sending && <ThinkingIndicator />}
            <div ref={bottom} />
          </div>
        </div>

        <div className="border-t border-zinc-200 bg-white/80 backdrop-blur">
          <div className="mx-auto max-w-3xl space-y-2 px-4 py-3">
            {sendError && <ErrorBanner message={sendError} onDismiss={() => setSendError(null)} />}
            <Composer value={draft} onChange={setDraft} onSubmit={send} disabled={noDocuments} sending={sending} />
            <p className="flex justify-between px-1 text-xs text-zinc-400">
              <span>Answers come only from your documents and may still contain mistakes. Check the sources.</span>
              {draft.length > MAX_QUESTION_LENGTH * 0.8 && (
                <span>
                  {draft.length}/{MAX_QUESTION_LENGTH}
                </span>
              )}
            </p>
          </div>
        </div>
      </section>

      {panel && <CitationPanel citations={panel.citations} focus={panel.focus} onClose={() => setPanel(null)} />}
    </div>
  )
}

function EmptyChat({ noDocuments, readyCount }: { noDocuments: boolean; readyCount: number }) {
  if (noDocuments) {
    return (
      <div className="flex flex-col items-center py-16 text-center">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
          <FileUp className="size-6" aria-hidden="true" />
        </span>
        <h2 className="mt-4 text-lg font-semibold text-zinc-900">Upload a document to get started</h2>
        <p className="mt-1 max-w-sm text-sm text-zinc-500">Add PDF or TXT files, then ask questions. Every answer links back to the passages it came from.</p>
        <Link to="/documents" className="mt-5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500">
          Upload documents
        </Link>
      </div>
    )
  }
  return (
    <div className="flex flex-col items-center py-16 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
        <MessageSquareText className="size-6" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-lg font-semibold text-zinc-900">Ask about your documents</h2>
      <p className="mt-1 max-w-sm text-sm text-zinc-500">
        Searching {readyCount} ready {readyCount === 1 ? 'document' : 'documents'}. Ask a specific question for the best results.
      </p>
    </div>
  )
}
