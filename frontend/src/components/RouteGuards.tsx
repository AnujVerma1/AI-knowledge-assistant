import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useAuth } from '../hooks/useAuth'
import { Spinner } from './Spinner'

function FullPageSpinner() {
  return (
    <div className="flex h-dvh items-center justify-center bg-zinc-50">
      <Spinner className="size-6 text-indigo-600" />
    </div>
  )
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useAuth()
  const location = useLocation()
  if (state.status === 'loading') return <FullPageSpinner />
  if (state.status === 'anonymous') return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

/**
 * For login/register. Once the user is authenticated this guard performs the redirect, so the
 * pages themselves must not navigate (two competing redirects would race).
 */
export function PublicOnly({ children, redirectTo }: { children: ReactNode; redirectTo?: string }) {
  const { state } = useAuth()
  const from = (useLocation().state as { from?: string } | null)?.from
  if (state.status === 'loading') return <FullPageSpinner />
  if (state.status === 'authenticated') return <Navigate to={redirectTo ?? from ?? '/chat'} replace />
  return children
}
