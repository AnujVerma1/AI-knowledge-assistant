import type { ReactNode } from 'react'
import { Logo } from './Logo'

export function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-zinc-50 px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>
        <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm sm:p-8">
          <h1 className="text-xl font-semibold text-zinc-900">{title}</h1>
          <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>
        <p className="mt-6 text-center text-sm text-zinc-600">{footer}</p>
      </div>
    </main>
  )
}

export function TextField(props: { label: string; type: string; value: string; onChange: (value: string) => void; autoComplete: string; hint?: string }) {
  const id = `field-${props.label.toLowerCase().replace(/\s+/g, '-')}`
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-zinc-700">
        {props.label}
      </label>
      <input
        id={id}
        type={props.type}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        autoComplete={props.autoComplete}
        required
        className="mt-1 block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm shadow-xs outline-none placeholder:text-zinc-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
      />
      {props.hint && <p className="mt-1 text-xs text-zinc-500">{props.hint}</p>}
    </div>
  )
}
