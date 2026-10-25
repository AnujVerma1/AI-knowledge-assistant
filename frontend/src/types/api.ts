// Mirrors the backend's Pydantic response schemas (backend/app/schemas).

export interface User {
  id: string
  email: string
  created_at: string
}

export interface AuthResponse {
  user: User
  csrf_token: string
}

export type DocumentStatus = 'processing' | 'ready' | 'failed' | 'deleting'

export interface DocumentItem {
  id: string
  filename: string
  file_type: 'pdf' | 'txt'
  size_bytes: number
  status: DocumentStatus
  chunk_count: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface Citation {
  label: string
  document_id: string
  filename: string
  page: number | null
  excerpt: string
  chunk_id: string
  score: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[] | null
  created_at: string
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

export interface AskResponse {
  user_message: Message
  assistant_message: Message
  sufficient_evidence: boolean
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: unknown
  }
}
