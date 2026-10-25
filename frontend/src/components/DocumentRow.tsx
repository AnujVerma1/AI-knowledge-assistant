import { ExternalLink, FileText, RotateCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { api, describeError } from '../services/api'
import type { DocumentItem } from '../types/api'
import { formatBytes, formatDate } from '../utils/format'
import { Spinner } from './Spinner'
import { StatusBadge } from './StatusBadge'

const iconButton = 'rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-50'

export function DocumentRow({ document, onChanged }: { document: DocumentItem; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
      onChanged()
    } catch (e) {
      setError(describeError(e))
    } finally {
      setBusy(false)
    }
  }

  function handleDelete() {
    const message = `Delete "${document.filename}"? It will no longer be used to answer questions. Past answers keep their quoted excerpts.`
    if (window.confirm(message)) void run(() => api.documents.remove(document.id))
  }

  return (
    <li className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-zinc-100 text-zinc-500">
          <FileText className="size-4" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-zinc-900" title={document.filename}>
            {document.filename}
          </p>
          <p className="text-xs text-zinc-500">
            {document.file_type.toUpperCase()} · {formatBytes(document.size_bytes)} · {formatDate(document.created_at)}
            {document.status === 'ready' && ` · ${document.chunk_count} ${document.chunk_count === 1 ? 'chunk' : 'chunks'}`}
          </p>
          {document.status === 'failed' && document.error_message && <p className="mt-1 text-xs text-red-700">{document.error_message}</p>}
          {error && <p className="mt-1 text-xs text-red-700">{error}</p>}
        </div>
      </div>
      <div className="flex items-center gap-1 pl-12 sm:pl-0">
        <StatusBadge status={document.status} />
        <a href={api.documents.fileUrl(document.id)} target="_blank" rel="noopener noreferrer" className={iconButton} aria-label={`Open ${document.filename}`} title="Open">
          <ExternalLink className="size-4" />
        </a>
        {document.status === 'failed' && (
          <button type="button" onClick={() => void run(() => api.documents.retry(document.id))} disabled={busy} className={iconButton} aria-label={`Retry ${document.filename}`} title="Retry">
            <RotateCw className="size-4" />
          </button>
        )}
        <button type="button" onClick={handleDelete} disabled={busy} className={`${iconButton} hover:text-red-600`} aria-label={`Delete ${document.filename}`} title="Delete">
          {busy ? <Spinner /> : <Trash2 className="size-4" />}
        </button>
      </div>
    </li>
  )
}
