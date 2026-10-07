import { useState, type ReactNode } from 'react'
import { useAuthedImage } from '../lib/authedImage'
import { useCountUp, useMagnetic, useTheme } from '../lib/motion'

/** Shared primitives, so the material, radii and motion are defined once
 * rather than retyped per component. */

export function Button({
  children,
  onClick,
  disabled,
  type = 'button',
  variant = 'secondary',
  size = 'md',
  className = '',
  ...rest
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  type?: 'button' | 'submit'
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  className?: string
  'aria-label'?: string
  'aria-expanded'?: boolean
  'aria-pressed'?: boolean
}) {
  const variants = {
    primary:
      'bg-accent text-accent-ink font-semibold shadow-[0_6px_24px_-6px_var(--color-violet)] hover:shadow-[0_10px_32px_-6px_var(--color-violet)]',
    secondary: 'border border-edge-hi bg-tint text-ink hover:bg-raised',
    ghost: 'text-ink-dim hover:bg-tint hover:text-ink',
    danger: 'border border-bad/40 text-bad hover:bg-bad/10',
  }
  const sizes = {
    sm: 'px-3 py-1.5 text-[13px] rounded-xl',
    md: 'px-4 py-2 text-sm rounded-xl',
    lg: 'px-5 py-2.5 text-[15px] rounded-2xl',
  }
  // Leans toward the pointer. Writes offsets on the node directly, so moving
  // the mouse over a button costs no React render.
  const magnet = useMagnetic<HTMLButtonElement>(disabled ? 0 : 3)
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      onPointerMove={magnet.onPointerMove}
      onPointerLeave={magnet.onPointerLeave}
      // `translate` is its own property, so the magnetic lean composes with
      // the tilt's `transform` instead of overwriting it.
      style={{ translate: 'var(--pull-x, 0) var(--pull-y, 0)' }}
      className={`sweep tilt inline-flex items-center justify-center gap-2 transition-[background-color,border-color,color,box-shadow,translate] duration-200 ease-[cubic-bezier(0.22,1,0.36,1)] disabled:cursor-not-allowed disabled:opacity-40 ${variants[variant]} ${sizes[size]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}

/** Status chip.
 *
 * Carries a glyph as well as a hue, so meaning survives for anyone who can't
 * distinguish the colours and in a greyscale screenshot. */
export function Status({
  tone,
  children,
  size = 'md',
}: {
  tone: 'neutral' | 'ok' | 'warn' | 'bad' | 'accent' | 'info'
  children: ReactNode
  size?: 'sm' | 'md'
}) {
  const tones = {
    neutral: 'border-edge-hi text-ink-faint bg-tint',
    ok: 'border-ok/30 text-ok bg-ok/10',
    warn: 'border-warn/30 text-warn bg-warn/10',
    bad: 'border-bad/30 text-bad bg-bad/10',
    accent: 'border-accent/35 text-accent-hi bg-accent/12',
    info: 'border-info/30 text-info bg-info/10',
  }
  const glyphs = { neutral: '○', ok: '✓', warn: '△', bad: '✕', accent: '●', info: '◆' }
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border font-medium ${
        tones[tone]
      } ${size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs'}`}
    >
      <span aria-hidden="true" className="text-[10px]">
        {glyphs[tone]}
      </span>
      {children}
    </span>
  )
}

export function Label({ children }: { children: ReactNode }) {
  return (
    <span className="font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-ink-faint">
      {children}
    </span>
  )
}

/** Two frames, slightly out of register — the thing this tool looks for. */
export function BrandMark({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="none">
      <rect
        x="2"
        y="2"
        width="15"
        height="15"
        rx="4"
        stroke="currentColor"
        strokeWidth="1.7"
        opacity="0.45"
      />
      <rect x="7" y="7" width="15" height="15" rx="4" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  )
}

/** A chevron. An SVG rather than "›", which has no glyph in Syne and would
 * fall back to a different face mid-row. */
export function Chevron({ className = '' }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`h-3.5 w-3.5 shrink-0 transition-transform duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${className}`}
    >
      <path d="m9 6 6 6-6 6" />
    </svg>
  )
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string
  body?: string
  action?: ReactNode
}) {
  return (
    <div className="animate-fade rounded-3xl border border-dashed border-edge-hi px-6 py-16 text-center">
      <div className="mx-auto mb-4 w-fit text-accent/60">
        <BrandMark className="h-10 w-10" />
      </div>
      <p className="font-display text-lg font-semibold text-ink-dim">{title}</p>
      {body && <p className="mx-auto mt-2 max-w-sm text-sm text-ink-faint">{body}</p>}
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  )
}

/** A screenshot that degrades to a placeholder instead of a broken icon.
 *
 * Captures are fetched from the API and legitimately 404 — a project whose
 * Figma frame was never fetched has no preview — and a broken-image glyph in
 * a project list reads as a bug in the app. */
export function Thumb({
  src,
  alt,
  className = '',
}: {
  src: string
  alt: string
  className?: string
}) {
  // Keyed on the src we failed at, not a boolean reset in an effect: a newly
  // created project gets its capture moments later, so a changed src must
  // retry, and this does that without a render cascade.
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  // Screenshots are owner-gated, so an <img> pointed straight at the API
  // would 401 — the bytes come through fetch with the token instead.
  const objectUrl = useAuthedImage(src)

  // No bytes yet, or none coming: the same placeholder serves both.
  if (failedSrc === src || !objectUrl) {
    return (
      <div
        className={`grid place-items-center bg-raised text-ink-faint/50 ${className}`}
        role="img"
        aria-label={`${alt} — no preview yet`}
      >
        <BrandMark className="h-4 w-4" />
      </div>
    )
  }

  return (
    <img
      src={objectUrl}
      alt={alt}
      loading="lazy"
      onError={() => setFailedSrc(src)}
      // Top-anchored: a full-page capture is mostly below the fold, and the
      // header is what identifies a page at thumbnail size.
      className={`bg-raised object-cover object-top ${className}`}
    />
  )
}

/** A count that rolls up to its value, so a number arriving reads as news
 * rather than as something that was always there. */
export function CountUp({ value, className = '' }: { value: number; className?: string }) {
  return <span className={`tabular-nums ${className}`}>{useCountUp(value)}</span>
}

/** A plain tab group: an underline on the current tab, nothing moving.
 *
 * A sliding pill needs to measure the active tab and animate a second
 * element behind the labels, and when its fill sits close to the track
 * colour the whole group reads as disabled. An underline is one border on
 * one button — it cannot go invisible or land in the wrong place. */
export function Tabs<T extends string>({
  tabs,
  current,
  onChange,
  label,
}: {
  tabs: { id: T; label: string; badge?: number }[]
  current: T
  onChange: (id: T) => void
  label: string
}) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 border-b border-edge">
      {tabs.map((tab) => {
        const active = current === tab.id
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={active}
            aria-current={active ? 'page' : undefined}
            onClick={() => onChange(tab.id)}
            className={`-mb-px border-b-2 px-4 py-2 text-[13px] font-medium transition-colors duration-200 ${
              active
                ? 'border-accent text-ink'
                : 'border-transparent text-ink-dim hover:border-edge-hi hover:text-ink'
            }`}
          >
            {tab.label}
            {tab.badge !== undefined && tab.badge > 0 && (
              <span
                key={tab.badge}
                className="animate-pop ml-2 inline-block rounded-full bg-accent/20 px-1.5 py-px font-mono text-[11px] text-accent-hi"
              >
                <CountUp value={tab.badge} />
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/** Switches the whole app between the warm studio and the lit room.
 *
 * Replaces the "Connected to backend" badge that used to sit here: a working
 * backend is the normal case, and spending the most valuable corner of the
 * chrome on it said nothing most of the time. Failures still surface — as an
 * error where you tried to act, which is where you can do something. */
export function ThemeToggle() {
  const [theme, toggle] = useTheme()
  const dark = theme === 'dark'
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="tilt grid h-9 w-9 place-items-center rounded-xl border border-edge text-ink-dim transition-colors duration-200 hover:border-edge-hi hover:text-amber"
    >
      {/* Both glyphs stay mounted and cross-rotate, so the swap is a
          transform rather than a mount — no layout, no flicker. */}
      <span className="relative grid h-4 w-4 place-items-center">
        <svg
          viewBox="0 0 24 24"
          aria-hidden="true"
          className={`absolute h-4 w-4 transition-transform duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
            dark ? 'rotate-0 scale-100' : 'rotate-90 scale-0'
          }`}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        >
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.4 5.4l1.6 1.6M17 17l1.6 1.6M18.6 5.4 17 7M7 17l-1.6 1.6" />
        </svg>
        <svg
          viewBox="0 0 24 24"
          aria-hidden="true"
          className={`absolute h-4 w-4 transition-transform duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
            dark ? '-rotate-90 scale-0' : 'rotate-0 scale-100'
          }`}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M20 14.2A8.2 8.2 0 0 1 9.8 4a8.4 8.4 0 1 0 10.2 10.2Z" />
        </svg>
      </span>
    </button>
  )
}
