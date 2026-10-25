import type {
  ApiErrorBody,
  AskResponse,
  AuthResponse,
  Conversation,
  ConversationDetail,
  DocumentItem,
} from '../types/api'

// All requests go to the same origin under /api: the Vite dev server (and Vercel in
// production) forwards them to FastAPI. The session lives in an HttpOnly cookie that this
// code never sees; only the CSRF token is handled here.

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

let csrfToken: string | null = null
let onUnauthorized: (() => void) | null = null

export function setCsrfToken(token: string | null) {
  csrfToken = token
}

export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

function currentCsrfToken(): string | null {
  if (csrfToken) return csrfToken
  const cookie = document.cookie.split('; ').find((c) => c.startsWith('csrf_token='))
  return cookie ? decodeURIComponent(cookie.slice('csrf_token='.length)) : null
}

function toApiError(status: number, body: unknown): ApiError {
  const error = (body as ApiErrorBody | null)?.error
  return new ApiError(status, error?.code ?? 'http_error', error?.message ?? `Request failed (${status}).`, error?.details)
}

function handleUnauthorized(status: number, path: string) {
  // Login and registration failures are shown on their own forms instead.
  if (status === 401 && !path.startsWith('/auth/')) onUnauthorized?.()
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') {
    const token = currentCsrfToken()
    if (token) headers['X-CSRF-Token'] = token
  }

  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
    })
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the server. Check that the backend is running and try again.')
  }

  if (response.status === 204) return undefined as T
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    handleUnauthorized(response.status, path)
    throw toApiError(response.status, data)
  }
  return data as T
}

function uploadWithProgress(file: File, onProgress: (fraction: number) => void): Promise<DocumentItem> {
  // fetch() cannot report upload progress, so uploads use XMLHttpRequest.
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/documents')
    xhr.withCredentials = true
    const token = currentCsrfToken()
    if (token) xhr.setRequestHeader('X-CSRF-Token', token)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total)
    }
    xhr.onload = () => {
      let data: unknown = null
      try {
        data = JSON.parse(xhr.responseText)
      } catch {
        // non-JSON response, handled below
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data as DocumentItem)
      } else {
        handleUnauthorized(xhr.status, '/documents')
        reject(toApiError(xhr.status, data))
      }
    }
    xhr.onerror = () => reject(new ApiError(0, 'network_error', 'The upload failed because the server could not be reached.'))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

/** A readable message for any error, including field-level validation details. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'validation_error' && Array.isArray(error.details)) {
      return (error.details as { field: string; message: string }[])
        .map((d) => (d.field ? `${d.field}: ${d.message}` : d.message))
        .join(' ')
    }
    if (error.code === 'rate_limited') {
      const seconds = (error.details as { retry_after_seconds?: number } | undefined)?.retry_after_seconds
      return seconds ? `${error.message} Try again in ${seconds} seconds.` : error.message
    }
    return error.message
  }
  return 'Something went wrong. Please try again.'
}

export const api = {
  auth: {
    me: () => request<AuthResponse>('GET', '/auth/me'),
    login: (email: string, password: string) => request<AuthResponse>('POST', '/auth/login', { email, password }),
    register: (email: string, password: string) => request<AuthResponse>('POST', '/auth/register', { email, password }),
    logout: () => request<void>('POST', '/auth/logout'),
  },
  documents: {
    list: () => request<{ documents: DocumentItem[] }>('GET', '/documents'),
    upload: uploadWithProgress,
    retry: (id: string) => request<DocumentItem>('POST', `/documents/${id}/retry`),
    remove: (id: string) => request<void>('DELETE', `/documents/${id}`),
    fileUrl: (id: string, page?: number | null) => `/api/documents/${id}/file${page ? `#page=${page}` : ''}`,
  },
  conversations: {
    list: () => request<{ conversations: Conversation[] }>('GET', '/conversations'),
    get: (id: string) => request<ConversationDetail>('GET', `/conversations/${id}`),
    create: () => request<Conversation>('POST', '/conversations', {}),
    remove: (id: string) => request<void>('DELETE', `/conversations/${id}`),
    ask: (id: string, content: string) => request<AskResponse>('POST', `/conversations/${id}/messages`, { content }),
  },
}
