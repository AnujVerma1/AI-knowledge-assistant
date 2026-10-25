import { FileText, Info, Sparkles } from 'lucide-react'
import type { Citation, Message } from '../types/api'
import { SafeMarkdown } from './SafeMarkdown'

export function MessageItem({ message, onOpenCitations }: { message: Message; onOpenCitations: (citations: Citation[], focus?: string) => void }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-indigo-600 px-4 py-2.5 text-[15px] leading-6 whitespace-pre-wrap text-white">
          {message.content}
        </p>
      </div>
    )
  }

  const citations = message.citations ?? []
  const insufficient = citations.length === 0

  return (
    <div className="flex gap-3">
      <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
        <Sparkles className="size-3.5" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        {insufficient ? (
          <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-900">
            <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p>{message.content}</p>
          </div>
        ) : (
          <SafeMarkdown text={message.content} onCitationClick={(label) => onOpenCitations(citations, label)} />
        )}

        {citations.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {citations.map((c) => (
              <button
                key={c.label}
                type="button"
                onClick={() => onOpenCitations(citations, c.label)}
                className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-zinc-200 bg-white px-2.5 py-1 text-xs text-zinc-700 hover:border-indigo-300 hover:text-indigo-700"
              >
                <span className="font-semibold text-indigo-600">{c.label}</span>
                <FileText className="size-3 shrink-0 text-zinc-400" aria-hidden="true" />
                <span className="truncate">{c.filename}</span>
                {c.page !== null && <span className="shrink-0 text-zinc-500">p.{c.page}</span>}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function ThinkingIndicator() {
  return (
    <div className="flex gap-3" role="status" aria-live="polite">
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
        <Sparkles className="size-3.5" aria-hidden="true" />
      </span>
      <div className="pt-1">
        <div className="flex gap-1" aria-hidden="true">
          {[0, 150, 300].map((delay) => (
            <span key={delay} className="size-2 animate-bounce rounded-full bg-zinc-400" style={{ animationDelay: `${delay}ms` }} />
          ))}
        </div>
        <p className="mt-2 text-xs text-zinc-500">Searching your documents and writing an answer. This can take up to a minute.</p>
      </div>
    </div>
  )
}
