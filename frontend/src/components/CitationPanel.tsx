import { ExternalLink, X } from 'lucide-react'
import { useEffect } from 'react'
import { api } from '../services/api'
import type { Citation } from '../types/api'

export function CitationPanel({ citations, focus, onClose }: { citations: Citation[]; focus?: string; onClose: () => void }) {
  useEffect(() => {
    if (focus) document.getElementById(`citation-${focus}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [focus, citations])

  return (
    <div className="fixed inset-0 z-30 lg:static lg:inset-auto lg:z-auto">
      <div className="absolute inset-0 bg-zinc-900/30 lg:hidden" onClick={onClose} aria-hidden="true" />
      <aside
        aria-label="Sources"
        className="absolute inset-x-0 bottom-0 flex max-h-[75dvh] flex-col rounded-t-2xl bg-white shadow-xl lg:static lg:h-full lg:max-h-none lg:w-96 lg:rounded-none lg:border-l lg:border-zinc-200 lg:shadow-none"
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-zinc-900">Sources</h2>
            <p className="text-xs text-zinc-500">Passages retrieved from your documents for this answer.</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-100" aria-label="Close sources">
            <X className="size-4" />
          </button>
        </div>
        <ul className="flex-1 space-y-3 overflow-y-auto p-4">
          {citations.map((c) => (
            <li
              key={c.label}
              id={`citation-${c.label}`}
              className={`rounded-xl border p-3 ${c.label === focus ? 'border-indigo-300 bg-indigo-50/50 ring-2 ring-indigo-500/10' : 'border-zinc-200'}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-indigo-600">{c.label}</p>
                  <p className="truncate text-sm font-medium text-zinc-900" title={c.filename}>
                    {c.filename}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {c.page !== null ? `Page ${c.page} · ` : ''}relevance {c.score.toFixed(2)}
                  </p>
                </div>
                <a
                  href={api.documents.fileUrl(c.document_id, c.page)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-zinc-200 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50"
                >
                  Open <ExternalLink className="size-3" aria-hidden="true" />
                </a>
              </div>
              <blockquote className="mt-2 border-l-2 border-zinc-200 pl-3 text-sm leading-6 whitespace-pre-wrap text-zinc-700">{c.excerpt}</blockquote>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  )
}
