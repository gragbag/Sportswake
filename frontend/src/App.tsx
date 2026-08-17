import { Link, Route, Routes } from "react-router-dom";
import { AuthForm } from "./components/AuthForm";
import { BriefPage } from "./components/BriefPage";
import { SettingsPage } from "./components/SettingsPage";
import { ThemeToggle } from "./components/ThemeToggle";
import { useAuth } from "./lib/auth";

function HeaderAuth() {
  const { email, loading, signOut } = useAuth();

  // Render nothing rather than a flash of "Sign in" for an already-logged-in
  // user while the session is being restored from storage.
  if (loading) return null;

  if (!email) {
    return (
      <nav className="flex items-center gap-1">
        <Link
          to="/login"
          className="t-footnote rounded-full px-3 py-1.5 font-medium text-label-2 transition-colors hover:bg-fill hover:text-label focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Sign in
        </Link>
        <Link
          to="/signup"
          className="t-footnote rounded-full bg-accent px-3.5 py-1.5 font-semibold text-white transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Get started
        </Link>
      </nav>
    );
  }

  return (
    <nav className="flex items-center gap-1">
      <Link
        to="/settings"
        className="t-footnote rounded-full px-3 py-1.5 font-medium text-label-2 transition-colors hover:bg-fill hover:text-label focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        Teams
      </Link>
      <button
        onClick={signOut}
        className="t-footnote rounded-full px-3 py-1.5 font-medium text-label-3 transition-colors hover:bg-fill hover:text-label focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        Sign out
      </button>
    </nav>
  );
}

/**
 * The chrome for everything that is not the brief.
 *
 * Settings and auth are app screens and keep the app's surfaces: a sticky bar,
 * rounded controls, the canvas/surface/label palette. The brief does not,
 * which is why it is routed around this shell rather than inside it.
 */
function AppShell() {
  return (
    <div className="min-h-screen">
      {/* A single hairline separates the bar from the content -- no shadow,
          no fill beyond the blur. The bar should be felt, not seen. */}
      <header className="sticky top-0 z-40 border-b border-separator bg-canvas/80 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-4 px-5 sm:px-8">
          <Link
            to="/"
            className="flex items-baseline gap-2 rounded focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
          >
            <span className="t-headline tracking-tight text-label">
              Sportswake
            </span>
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <span
              aria-hidden="true"
              className="hidden h-4 w-px bg-separator sm:block"
            />
            <HeaderAuth />
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-5 py-8 sm:px-8 sm:py-10">
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/login" element={<AuthForm mode="login" />} />
          <Route path="/signup" element={<AuthForm mode="signup" />} />
        </Routes>
      </div>
    </div>
  );
}

export default function App() {
  // The brief is rendered outside the shell on purpose. The shell caps content
  // at max-w-5xl and floats a backdrop-blurred bar over the top; the brief is
  // set on a 1180px column and its whole visual argument is that depth comes
  // from hairlines and paper tone, never from a translucent panel. It carries
  // its own masthead, which is where the account links and theme control live
  // on that route.
  return (
    <Routes>
      <Route path="/" element={<BriefPage />} />
      <Route path="*" element={<AppShell />} />
    </Routes>
  );
}
