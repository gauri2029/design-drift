import { useEffect, useState } from 'react'

interface ZoomableImageProps {
  src: string
  alt: string
  className?: string
}

// A click-to-expand image: a plain thumbnail that opens a fullscreen
// overlay with a larger render on click, closed via the backdrop, the
// close button, or Escape. No animation/carousel library — just enough
// for inspecting a comparison screenshot at real size.
export function ZoomableImage({ src, alt, className = '' }: ZoomableImageProps) {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open])

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`group relative block w-full cursor-zoom-in overflow-hidden ${className}`}
      >
        <img src={src} alt={alt} className="w-full object-contain" />
        <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-slate-950/0 opacity-0 transition group-hover:bg-slate-950/40 group-hover:opacity-100">
          <span className="rounded-full bg-white/95 px-3 py-1 text-xs font-medium text-slate-900 shadow-sm">
            Click to expand
          </span>
        </span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={alt}
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-6"
        >
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="absolute right-6 top-6 flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-lg text-white transition hover:bg-white/20"
          >
            ×
          </button>
          <img
            src={src}
            alt={alt}
            onClick={(event) => event.stopPropagation()}
            className="max-h-full max-w-full cursor-default rounded-lg object-contain shadow-2xl"
          />
        </div>
      )}
    </>
  )
}
