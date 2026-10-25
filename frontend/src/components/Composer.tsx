import { SendHorizontal } from 'lucide-react'
import { useEffect, useRef, type FormEvent, type KeyboardEvent } from 'react'
import { Spinner } from './Spinner'

export const MAX_QUESTION_LENGTH = 2000

export function Composer(props: { value: string; onChange: (value: string) => void; onSubmit: () => void; disabled: boolean; sending: boolean }) {
  const textarea = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    // Grow with the content, up to a limit.
    const element = textarea.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`
  }, [props.value])

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      props.onSubmit()
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    props.onSubmit()
  }

  const canSend = !props.disabled && !props.sending && props.value.trim().length > 0

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2 rounded-2xl border border-zinc-300 bg-white p-2 shadow-xs focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/20">
      <textarea
        ref={textarea}
        rows={1}
        value={props.value}
        maxLength={MAX_QUESTION_LENGTH}
        onChange={(e) => props.onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={props.disabled}
        placeholder={props.disabled ? 'Upload a document to start asking questions' : 'Ask a question about your documents…'}
        aria-label="Your question"
        className="max-h-[200px] min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-zinc-400 disabled:cursor-not-allowed"
      />
      <button
        type="submit"
        disabled={!canSend}
        className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white hover:bg-indigo-500 disabled:bg-zinc-200 disabled:text-zinc-400"
        aria-label="Send question"
      >
        {props.sending ? <Spinner /> : <SendHorizontal className="size-4" />}
      </button>
    </form>
  )
}
