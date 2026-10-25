import { Menu, X } from 'lucide-react'
import { useState } from 'react'
import { Outlet } from 'react-router'
import { useConversations, type LayoutContext } from '../hooks/useConversations'
import { Logo } from './Logo'
import { Sidebar } from './Sidebar'

export function AppLayout() {
  const conversations = useConversations()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const closeDrawer = () => setDrawerOpen(false)

  return (
    <div className="flex h-dvh bg-zinc-50 text-zinc-900">
      <aside className="hidden w-72 shrink-0 border-r border-zinc-200 bg-white md:block">
        <Sidebar conversations={conversations} />
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-zinc-900/40" onClick={closeDrawer} aria-hidden="true" />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-white shadow-xl">
            <button type="button" onClick={closeDrawer} className="absolute top-4 right-3 rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-100" aria-label="Close menu">
              <X className="size-4" />
            </button>
            <Sidebar conversations={conversations} onNavigate={closeDrawer} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-zinc-200 bg-white px-4 py-2.5 md:hidden">
          <button type="button" onClick={() => setDrawerOpen(true)} className="rounded-lg p-1.5 text-zinc-600 hover:bg-zinc-100" aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          <Logo />
        </header>
        <main className="min-h-0 flex-1">
          <Outlet context={{ conversations } satisfies LayoutContext} />
        </main>
      </div>
    </div>
  )
}
