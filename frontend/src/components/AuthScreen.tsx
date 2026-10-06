import { useState } from 'react'
import { Button, BrandMark } from './ui'

/** The sign-in and sign-up screen — one component, two modes.
 *
 * Login and signup differ by exactly one field and one verb, so splitting
 * them into two files would duplicate the layout, the error handling and
 * the submit flow to vary a label.
 */
export function AuthScreen({
  mode,
  onSubmit,
  onSwitchMode,
  onBack,
  error,
}: {
  mode: 'login' | 'signup'
  onSubmit: (values: { name: string; email: string; password: string }) => Promise<void>
  onSwitchMode: () => void
  onBack: () => void
  error: string | null
}) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const signingUp = mode === 'signup'

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      await onSubmit({ name, email, password })
    } catch {
      // useAuth has already put the message in `error`; this catch exists
      // so a failure re-enables the form instead of leaving it spinning.
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-5 py-10">
      <div className="animate-rise w-full max-w-[26rem]">
        <button
          type="button"
          onClick={onBack}
          className="mb-8 inline-flex items-center gap-2.5 text-ink-dim transition-colors duration-200 hover:text-ink"
        >
          <span className="text-accent">
            <BrandMark className="h-6 w-6" />
          </span>
          <span className="font-display text-[17px] font-bold tracking-[-0.02em]">
            Design Drift
          </span>
        </button>

        <div className="glass rounded-3xl p-7">
          <h1 className="font-display text-[26px] font-bold leading-tight tracking-[-0.03em] text-ink">
            {signingUp ? 'Create your account' : 'Welcome back'}
          </h1>
          <p className="mt-2 text-sm text-ink-faint">
            {signingUp
              ? 'Start checking your designs against what actually shipped.'
              : 'Sign in to pick up where you left off.'}
          </p>

          <form onSubmit={handleSubmit} className="mt-7 space-y-4">
            {signingUp && (
              <Field
                label="Name"
                type="text"
                value={name}
                onChange={setName}
                autoComplete="name"
                placeholder="Ada Lovelace"
                required
              />
            )}
            <Field
              label="Email"
              type="email"
              value={email}
              onChange={setEmail}
              autoComplete="email"
              placeholder="you@studio.com"
              required
            />
            <Field
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              // Tells a password manager to offer a new password rather than
              // autofilling the existing one.
              autoComplete={signingUp ? 'new-password' : 'current-password'}
              placeholder={signingUp ? 'At least 8 characters' : '••••••••'}
              // Matches the backend's SignupRequest floor, so the browser
              // catches it before a round trip.
              minLength={signingUp ? 8 : undefined}
              required
            />

            {error && (
              <p
                role="alert"
                className="animate-fade rounded-xl border border-bad/30 bg-bad/10 px-3.5 py-2.5 text-[13px] text-bad"
              >
                {error}
              </p>
            )}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              disabled={submitting}
              className="w-full"
            >
              {submitting
                ? signingUp
                  ? 'Creating your account…'
                  : 'Signing you in…'
                : signingUp
                  ? 'Create account'
                  : 'Sign in'}
            </Button>
          </form>
        </div>

        <p className="mt-5 text-center text-[13px] text-ink-faint">
          {signingUp ? 'Already have an account?' : 'New to Design Drift?'}{' '}
          <button
            type="button"
            onClick={onSwitchMode}
            className="font-medium text-accent-hi underline-offset-4 transition-colors duration-200 hover:underline"
          >
            {signingUp ? 'Sign in' : 'Create one'}
          </button>
        </p>
      </div>
    </div>
  )
}

function Field({
  label,
  type,
  value,
  onChange,
  autoComplete,
  placeholder,
  required,
  minLength,
}: {
  label: string
  type: 'text' | 'email' | 'password'
  value: string
  onChange: (value: string) => void
  autoComplete: string
  placeholder?: string
  required?: boolean
  minLength?: number
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-ink-dim">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete={autoComplete}
        placeholder={placeholder}
        required={required}
        minLength={minLength}
        className="w-full rounded-xl border border-edge-hi bg-tint px-3.5 py-2.5 text-sm text-ink placeholder:text-ink-faint/60 transition-[border-color,box-shadow] duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25"
      />
    </label>
  )
}
