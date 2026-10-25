import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { AuthShell, TextField } from '../components/AuthShell'
import { ErrorBanner } from '../components/ErrorBanner'
import { Spinner } from '../components/Spinner'
import { useAuth } from '../hooks/useAuth'
import { describeError } from '../services/api'

const MIN_PASSWORD_LENGTH = 8

export function RegisterPage() {
  const { register } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (password.length < MIN_PASSWORD_LENGTH) return setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
    if (password !== confirmation) return setError('Passwords do not match.')
    setSubmitting(true)
    setError(null)
    try {
      await register(email, password) // <PublicOnly> redirects once the session exists
    } catch (e) {
      setError(describeError(e))
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Upload documents and get answers with sources."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-indigo-600 hover:text-indigo-500">
            Log in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <ErrorBanner message={error} />}
        <TextField label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" />
        <TextField
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
        />
        <TextField label="Confirm password" type="password" value={confirmation} onChange={setConfirmation} autoComplete="new-password" />
        <button
          type="submit"
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {submitting && <Spinner />}
          Create account
        </button>
      </form>
    </AuthShell>
  )
}
