import { CircleAlert, CircleCheck } from 'lucide-react'
import type { DocumentStatus } from '../types/api'
import { Spinner } from './Spinner'

const STYLES: Record<DocumentStatus, string> = {
  processing: 'bg-amber-50 text-amber-800 ring-amber-200',
  ready: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  failed: 'bg-red-50 text-red-800 ring-red-200',
  deleting: 'bg-zinc-100 text-zinc-600 ring-zinc-200',
}

const LABELS: Record<DocumentStatus, string> = {
  processing: 'Processing',
  ready: 'Ready',
  failed: 'Failed',
  deleting: 'Deleting',
}

export function StatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[status]}`}>
      {status === 'processing' || status === 'deleting' ? (
        <Spinner className="size-3" />
      ) : status === 'ready' ? (
        <CircleCheck className="size-3" aria-hidden="true" />
      ) : (
        <CircleAlert className="size-3" aria-hidden="true" />
      )}
      {LABELS[status]}
    </span>
  )
}
