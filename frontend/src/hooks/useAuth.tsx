import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setCsrfToken, setUnauthorizedHandler } from '../services/api'
import type { AuthResponse, User } from '../types/api'

type AuthState = { status: 'loading' } | { status: 'anonymous' } | { status: 'authenticated'; user: User }

interface AuthContextValue {
  state: AuthState
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' })

  const startSession = useCallback((response: AuthResponse) => {
    setCsrfToken(response.csrf_token)
    setState({ status: 'authenticated', user: response.user })
  }, [])

  const endSession = useCallback(() => {
    setCsrfToken(null)
    setState({ status: 'anonymous' })
  }, [])

  useEffect(() => {
    // Any 401 from the API (e.g. an expired session) sends the user back to the login page.
    setUnauthorizedHandler(endSession)
    api.auth.me().then(startSession, endSession)
    return () => setUnauthorizedHandler(null)
  }, [startSession, endSession])

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      login: async (email, password) => startSession(await api.auth.login(email, password)),
      register: async (email, password) => startSession(await api.auth.register(email, password)),
      logout: async () => {
        try {
          await api.auth.logout()
        } finally {
          endSession()
        }
      },
    }),
    [state, startSession, endSession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// oxlint-disable-next-line react/only-export-components -- the hook belongs with its provider
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
