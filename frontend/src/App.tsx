import { Link, Route, Routes } from "react-router-dom";
import { AuthForm } from "./components/AuthForm";
import { FavoritesPage } from "./components/FavoritesPage";
import { Feed } from "./components/Feed";
import { SettingsPage } from "./components/SettingsPage";
import { StoryPage } from "./components/StoryPage";
import { UserPage } from "./components/UserPage";
import { useAuth } from "./lib/auth";

function HeaderAuth() {
  const { email, loading, signOut } = useAuth();

  // Render nothing rather than a flash of "Sign in" for an already-logged-in
  // user while the session is being restored from storage.
  if (loading) return null;

  if (!email) {
    return (
      <nav className="flex items-center gap-3 text-xs">
        <Link to="/login" className="text-ink-500 hover:text-ink-900 dark:text-white/50 dark:hover:text-white">
          Sign in
        </Link>
        <Link
          to="/signup"
          className="rounded bg-ink-900 px-2.5 py-1 font-medium text-white dark:bg-white dark:text-ink-900"
        >
          Create account
        </Link>
      </nav>
    );
  }

  return (
    <nav className="flex items-center gap-3 text-xs">
      <Link
        to="/favorites"
        className="text-ink-500 hover:text-ink-900 dark:text-white/50 dark:hover:text-white"
      >
        Saved
      </Link>
      <Link
        to="/settings"
        className="text-ink-500 hover:text-ink-900 dark:text-white/50 dark:hover:text-white"
      >
        {email}
      </Link>
      <button
        onClick={signOut}
        className="text-ink-500 underline hover:text-ink-900 dark:text-white/50 dark:hover:text-white"
      >
        Sign out
      </button>
    </nav>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-white font-sans dark:bg-ink-900">
      {/* max-w + mx-auto caps the line length and centres what is left, so on
          a wide monitor the outer whitespace is set by the window, not by
          px-12 -- it will always dwarf the column gutter. Uncapping this is
          the only way to make the three gaps truly equal, at the cost of a
          much wider text column. */}
      <div className="mx-auto max-w-6xl px-6 py-12 lg:px-12">
        <header className="mb-8 flex items-start justify-between gap-4">
          <div>
            <Link to="/" className="inline-block">
              <h1 className="text-2xl font-semibold text-ink-900 dark:text-white">
                Presswake
              </h1>
            </Link>
            <p className="mt-1 text-sm text-ink-500 dark:text-white/50">
              How every outlet covered the same story &mdash; who published,
              when, and who didn&rsquo;t.
            </p>
          </div>
          <HeaderAuth />
        </header>

        <Routes>
          <Route path="/" element={<Feed />} />
          <Route path="/story/:storyId" element={<StoryPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/u/:handle" element={<UserPage />} />
          <Route path="/login" element={<AuthForm mode="login" />} />
          <Route path="/signup" element={<AuthForm mode="signup" />} />
        </Routes>
      </div>
    </div>
  );
}
