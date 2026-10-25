import { BookOpenText } from 'lucide-react'

export function Logo() {
  return (
    <div className="flex items-center gap-2">
      <span className="flex size-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
        <BookOpenText className="size-4.5" aria-hidden="true" />
      </span>
      <span className="font-semibold text-zinc-900">Knowledge Assistant</span>
    </div>
  )
}
