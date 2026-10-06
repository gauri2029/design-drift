import { useEffect, useState } from 'react'
import { AuthScreen } from './components/AuthScreen'
import { Landing } from './components/Landing'
import { ProjectsPanel } from './components/ProjectsPanel'
import { BrandMark, Button, ThemeToggle } from './components/ui'
import { useAuth } from './hooks/useAuth'

/** The four screens this app has. Not a router library: there are four
 * states and no nested or parameterised routes, so `react-router` would be
 * a dependency earning its keep on one `switch` (docs/principles.md #6).
 * It still uses real URLs and real history, so /login is linkable and the
 * back button works. */
type Route = '/' | '/login' | '/signup' | '/app'

const ROUTES: Route[] = ['/', '/login', '/signup', '/app']

function currentRoute(): Route {
  const path = window.location.pathname as Route
  return ROUTES.includes(path) ? path : '/'
}

function App() {
  const auth = useAuth()
  const [route, setRoute] = useState<Route>(currentRoute)

  // The back/forward buttons change the URL without telling React.
  useEffect(() => {
    const onPopState = () => setRoute(currentRoute())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  function navigate(next: Route) {
    window.history.pushState(null, '', next)
    setRoute(next)
  }

  // Confirming a stored token takes a round trip. Rendering the landing page
  // first and swapping to the workspace would flash marketing copy at
  // someone already signed in, so this waits — but only when there is a
  // token to confirm (see useAuth).
  if (auth.status === 'checking') {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="room" aria-hidden="true" />
        <span className="animate-breathe text-accent">
          <BrandMark className="h-8 w-8" />
        </span>
        <span className="sr-only">Checking your session…</span>
      </div>
    )
  }

  const signedIn = auth.status === 'signed-in'

  if (!signedIn) {
    // /app while signed out falls through to the landing page rather than
    // rendering a workspace whose requests would have no identity behind
    // them. The URL is corrected so a reload doesn't bounce again.
    if (route === '/login' || route === '/signup') {
      return (
        <>
          <div className="room" aria-hidden="true" />
          <AuthScreen
            mode={route === '/signup' ? 'signup' : 'login'}
            error={auth.error}
            onSubmit={async ({ name, email, password }) => {
              if (route === '/signup') await auth.signup(name, email, password)
              else await auth.login(email, password)
              navigate('/app')
            }}
            onSwitchMode={() => navigate(route === '/signup' ? '/login' : '/signup')}
            onBack={() => navigate('/')}
          />
        </>
      )
    }
    return (
      <>
        <div className="room" aria-hidden="true" />
        <Landing onGetStarted={() => navigate('/signup')} onSignIn={() => navigate('/login')} />
      </>
    )
  }

  return (
    <div className="min-h-screen">
      {/* First in the tab order, visible only on focus: the rail is a long
          list and keyboard users shouldn't walk it on every visit. */}
      <a href="#workspace" className="skip-link">
        Skip to the workspace
      </a>

      {/* Drifting colour blobs and grain behind everything. Fixed and
          composited once, so the 26s animation is free. */}
      <div className="room" aria-hidden="true" />

      {/* Glass, because the work scrolls underneath it. The marketing copy
          that used to sit below now lives on the landing page, where it
          addresses someone deciding whether to use the tool rather than
          someone using it. */}
      <header className="sticky top-0 z-40 border-b border-edge bg-void/50 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-3 px-6 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="text-accent">
              <BrandMark className="h-6 w-6" />
            </span>
            <span className="font-display text-[17px] font-bold tracking-[-0.02em] text-ink">
              Design Drift
            </span>
          </div>
          <div className="flex items-center gap-2.5">
            {auth.user && (
              <span className="hidden text-[13px] text-ink-faint sm:inline">
                {auth.user.name}
              </span>
            )}
            <ThemeToggle />
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                auth.logout()
                navigate('/')
              }}
            >
              Sign out
            </Button>
          </div>
        </div>
      </header>

      {/* The skip link targets ProjectsPanel's own #workspace, which is
          past the project rail — the point of skipping. */}
      <main className="mx-auto max-w-[1600px] px-6 py-8 pe-7">
        <ProjectsPanel />
      </main>
    </div>
  )
}

export default App
