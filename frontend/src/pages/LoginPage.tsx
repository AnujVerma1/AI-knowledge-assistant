import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { AuthShell, TextField } from '../components/AuthShell'
import { ErrorBanner } from '../components/ErrorBanner'
import { Spinner } from '../components/Spinner'
import { useAuth } from '../hooks/useAuth'
import { describeError } from '../services/api'

export function LoginPage() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await login(email, password) // <PublicOnly> redirects once the session exists
    } catch (e) {
      setError(describeError(e))
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Log in to ask questions about your documents."
      footer={
        <>
          New here?{' '}
          <Link to="/register" className="font-medium text-indigo-600 hover:text-indigo-500">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <ErrorBanner message={error} />}
        <TextField label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" />
        <TextField label="Password" type="password" value={password} onChange={setPassword} autoComplete="current-password" />
        <button
          type="submit"
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {submitting && <Spinner />}
          Log in
        </button>
      </form>
    </AuthShell>
  )
}
