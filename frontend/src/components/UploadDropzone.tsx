import { CloudUpload } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { ACCEPTED_EXTENSIONS, MAX_UPLOAD_MB } from '../utils/format'

export function UploadDropzone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  function handleDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    if (event.dataTransfer.files.length) onFiles(Array.from(event.dataTransfer.files))
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`flex flex-col items-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
        dragging ? 'border-indigo-400 bg-indigo-50' : 'border-zinc-300 bg-white'
      }`}
    >
      <span className="flex size-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
        <CloudUpload className="size-5" aria-hidden="true" />
      </span>
      <p className="mt-3 text-sm font-medium text-zinc-900">
        Drag files here or{' '}
        <button type="button" onClick={() => input.current?.click()} className="text-indigo-600 underline-offset-2 hover:underline">
          browse
        </button>
      </p>
      <p className="mt-1 text-xs text-zinc-500">
        PDF or TXT, up to {MAX_UPLOAD_MB} MB each. Scanned PDFs without a text layer are not supported.
      </p>
      <input
        ref={input}
        type="file"
        multiple
        accept={[...ACCEPTED_EXTENSIONS, 'application/pdf', 'text/plain'].join(',')}
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) onFiles(Array.from(e.target.files))
          e.target.value = '' // allow selecting the same file again
        }}
      />
    </div>
  )
}
