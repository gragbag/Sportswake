import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authConfigured, supabase } from "../lib/supabase";

type Mode = "login" | "signup";

const COPY = {
  login: {
    title: "Sign in",
    submit: "Sign in",
    altPrompt: "No account yet?",
    altLabel: "Create one",
    altTo: "/signup",
  },
  signup: {
    title: "Create an account",
    submit: "Create account",
    altPrompt: "Already have an account?",
    altLabel: "Sign in",
    altTo: "/login",
  },
} as const;

export function AuthForm({ mode }: { mode: Mode }) {
  const copy = COPY[mode];
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    // Without this the browser does a full page navigation and the React
    // app reloads mid-request.
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);

    try {
      if (mode === "signup") {
        const { data, error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        // With email confirmation on, signUp returns a user but no session:
        // nothing is logged in until they click the link. Detect that by the
        // absence of a session rather than assuming either configuration.
        if (!data.session) {
          setNotice(`Check ${email} for a confirmation link.`);
          return;
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      }
      // AuthProvider's listener already has the new session; just leave.
      navigate("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  if (!authConfigured) {
    return (
      <div className="mx-auto max-w-sm pt-12 text-sm text-ink-mute">
        <p>
          Auth is not configured. Add <code>VITE_SUPABASE_URL</code> and{" "}
          <code>VITE_SUPABASE_ANON_KEY</code> to <code>.env</code>, then restart{" "}
          <code>make web</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-sm pt-12">
      <h1 className="text-xl font-semibold text-ink">
        {copy.title}
      </h1>

      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-ink-mute">
            Email
          </span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border border-rule bg-paper-lift px-3 py-2 text-sm
                       text-ink outline-none focus:border-spot
                      "
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-ink-mute">
            Password
          </span>
          <input
            type="password"
            required
            minLength={6}
            // Tells password managers whether to offer a saved password or
            // generate a new one.
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded border border-rule bg-paper-lift px-3 py-2 text-sm
                       text-ink outline-none focus:border-spot
                      "
          />
        </label>

        {error && (
          <p className="rounded border border-red-300 bg-red-50 p-2 text-xs text-red-700">
            {error}
          </p>
        )}
        {notice && (
          <p className="rounded border border-rule p-2 text-xs text-ink-mute">
            {notice}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="mt-1 rounded-full bg-spot px-4 py-2.5 text-sm font-semibold text-white
                     transition-opacity hover:opacity-90 disabled:opacity-40
                     focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
        >
          {busy ? "Working…" : copy.submit}
        </button>
      </form>

      <p className="mt-4 text-xs text-ink-mute">
        {copy.altPrompt}{" "}
        <Link to={copy.altTo} className="underline">
          {copy.altLabel}
        </Link>
      </p>
    </div>
  );
}
