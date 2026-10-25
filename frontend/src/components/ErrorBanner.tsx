import { CircleAlert, X } from 'lucide-react'

export function ErrorBanner({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <p className="flex-1">{message}</p>
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="rounded p-0.5 hover:bg-red-100" aria-label="Dismiss error">
          <X className="size-4" />
        </button>
      )}
    </div>
  )
}
