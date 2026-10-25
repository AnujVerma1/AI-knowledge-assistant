import { FileText, LogOut, MessageSquare, Plus, Trash2 } from 'lucide-react'
import { NavLink, useMatch, useNavigate } from 'react-router'
import { useAuth } from '../hooks/useAuth'
import type { ConversationsState } from '../hooks/useConversations'
import { describeError } from '../services/api'
import { Logo } from './Logo'
import { Spinner } from './Spinner'

const navItem = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${
    isActive ? 'bg-indigo-50 text-indigo-700' : 'text-zinc-700 hover:bg-zinc-100'
  }`

export function Sidebar({ conversations, onNavigate }: { conversations: ConversationsState; onNavigate?: () => void }) {
  const { state, logout } = useAuth()
  const navigate = useNavigate()
  const activeId = useMatch('/chat/:conversationId')?.params.conversationId

  async function handleDelete(id: string, title: string) {
    if (!window.confirm(`Delete the conversation "${title}"? This cannot be undone.`)) return
    try {
      await conversations.remove(id)
      if (id === activeId) navigate('/chat')
    } catch (e) {
      window.alert(describeError(e))
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="px-4 pt-4 pb-3">
        <Logo />
      </div>

      <div className="space-y-1 px-3">
        <button
          type="button"
          onClick={() => {
            navigate('/chat')
            onNavigate?.()
          }}
          className="mb-2 flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          <Plus className="size-4" aria-hidden="true" /> New chat
        </button>
        <NavLink to="/chat" end className={navItem} onClick={onNavigate}>
          <MessageSquare className="size-4" aria-hidden="true" /> Chat
        </NavLink>
        <NavLink to="/documents" className={navItem} onClick={onNavigate}>
          <FileText className="size-4" aria-hidden="true" /> Documents
        </NavLink>
      </div>

      <div className="mt-5 min-h-0 flex-1 overflow-y-auto px-3">
        <p className="px-3 pb-1 text-xs font-medium tracking-wide text-zinc-400 uppercase">Conversations</p>
        {conversations.loading ? (
          <div className="flex justify-center py-4 text-zinc-400">
            <Spinner />
          </div>
        ) : conversations.error ? (
          <p className="px-3 py-2 text-sm text-red-600">{conversations.error}</p>
        ) : conversations.items.length === 0 ? (
          <p className="px-3 py-2 text-sm text-zinc-500">No conversations yet.</p>
        ) : (
          <ul className="space-y-0.5 pb-4">
            {conversations.items.map((c) => (
              <li key={c.id} className="group relative">
                <NavLink
                  to={`/chat/${c.id}`}
                  onClick={onNavigate}
                  title={c.title}
                  className={({ isActive }) =>
                    `block truncate rounded-lg py-2 pr-9 pl-3 text-sm ${isActive ? 'bg-zinc-100 font-medium text-zinc-900' : 'text-zinc-600 hover:bg-zinc-50'}`
                  }
                >
                  {c.title}
                </NavLink>
                <button
                  type="button"
                  onClick={() => handleDelete(c.id, c.title)}
                  className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-1 text-zinc-400 opacity-100 hover:bg-zinc-200 hover:text-red-600 md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100"
                  aria-label={`Delete conversation ${c.title}`}
                >
                  <Trash2 className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-zinc-200 px-4 py-3">
        <p className="min-w-0 flex-1 truncate text-sm text-zinc-600" title={state.status === 'authenticated' ? state.user.email : ''}>
          {state.status === 'authenticated' ? state.user.email : ''}
        </p>
        <button type="button" onClick={() => void logout()} className="rounded-lg p-2 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900" aria-label="Log out" title="Log out">
          <LogOut className="size-4" />
        </button>
      </div>
    </div>
  )
}
