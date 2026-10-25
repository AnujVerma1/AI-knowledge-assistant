import { CircleAlert, CircleCheck, FileStack, X } from 'lucide-react'
import { useState } from 'react'
import { DocumentRow } from '../components/DocumentRow'
import { ErrorBanner } from '../components/ErrorBanner'
import { Spinner } from '../components/Spinner'
import { UploadDropzone } from '../components/UploadDropzone'
import { useDocuments } from '../hooks/useDocuments'
import { api, describeError } from '../services/api'
import { validateUpload } from '../utils/format'

interface UploadItem {
  key: string
  name: string
  progress: number
  state: 'uploading' | 'done' | 'error'
  message?: string
}

export function DocumentsPage() {
  const { documents, setDocuments, loading, error, refresh } = useDocuments()
  const [uploads, setUploads] = useState<UploadItem[]>([])

  const update = (key: string, changes: Partial<UploadItem>) =>
    setUploads((previous) => previous.map((u) => (u.key === key ? { ...u, ...changes } : u)))

  async function handleFiles(files: File[]) {
    // One at a time: the server indexes documents sequentially anyway.
    for (const file of files) {
      const key = crypto.randomUUID()
      const problem = validateUpload(file)
      setUploads((previous) => [{ key, name: file.name, progress: 0, state: problem ? 'error' : 'uploading', message: problem ?? undefined }, ...previous])
      if (problem) continue
      try {
        const document = await api.documents.upload(file, (progress) => update(key, { progress }))
        update(key, { state: 'done', progress: 1, message: 'Uploaded. Indexing will finish in a moment.' })
        setDocuments((previous) => [document, ...previous.filter((d) => d.id !== document.id)])
      } catch (e) {
        update(key, { state: 'error', message: describeError(e) })
      }
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 sm:py-8">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Documents</h1>
          <p className="mt-1 text-sm text-zinc-500">Only you can see your documents. Answers are generated only from documents marked Ready.</p>
        </div>

        <UploadDropzone onFiles={(files) => void handleFiles(files)} />

        {uploads.length > 0 && (
          <ul className="space-y-2" aria-label="Uploads">
            {uploads.map((u) => (
              <li key={u.key} className="rounded-xl border border-zinc-200 bg-white px-4 py-3">
                <div className="flex items-center gap-2">
                  {u.state === 'uploading' ? (
                    <Spinner className="size-4 text-indigo-600" />
                  ) : u.state === 'done' ? (
                    <CircleCheck className="size-4 text-emerald-600" aria-hidden="true" />
                  ) : (
                    <CircleAlert className="size-4 text-red-600" aria-hidden="true" />
                  )}
                  <p className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-900">{u.name}</p>
                  {u.state === 'uploading' ? (
                    <span className="text-xs text-zinc-500 tabular-nums">{Math.round(u.progress * 100)}%</span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setUploads((previous) => previous.filter((x) => x.key !== u.key))}
                      className="rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700"
                      aria-label={`Dismiss ${u.name}`}
                    >
                      <X className="size-3.5" />
                    </button>
                  )}
                </div>
                {u.state === 'uploading' && (
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-zinc-100">
                    <div className="h-full rounded-full bg-indigo-600 transition-[width]" style={{ width: `${Math.round(u.progress * 100)}%` }} />
                  </div>
                )}
                {u.message && <p className={`mt-1 text-xs ${u.state === 'error' ? 'text-red-700' : 'text-zinc-500'}`}>{u.message}</p>}
              </li>
            ))}
          </ul>
        )}

        <section>
          <h2 className="mb-2 text-sm font-semibold text-zinc-900">Your documents</h2>
          {error && <ErrorBanner message={error} />}
          {loading ? (
            <div className="flex justify-center py-10 text-zinc-400">
              <Spinner className="size-5" />
            </div>
          ) : documents.length === 0 ? (
            <div className="flex flex-col items-center rounded-2xl border border-zinc-200 bg-white py-10 text-center">
              <FileStack className="size-6 text-zinc-400" aria-hidden="true" />
              <p className="mt-2 text-sm text-zinc-600">No documents yet. Upload one above.</p>
            </div>
          ) : (
            <ul className="divide-y divide-zinc-200 overflow-hidden rounded-2xl border border-zinc-200 bg-white">
              {documents.map((d) => (
                <DocumentRow key={d.id} document={d} onChanged={() => void refresh()} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
