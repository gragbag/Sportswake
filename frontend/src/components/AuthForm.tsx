import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authConfigured, supabase } from "../lib/supabase";

type Mode = "login" | "signup";

const COPY = {
  login: {
    title: "Sign in.",
    standfirst: null,
    deck: null,
    submit: "Sign in",
    altPrompt: "No account yet?",
    altLabel: "Get started",
    altTo: "/signup",
  },
  signup: {
    title: "Start your morning edition.",
    standfirst: "Free · NBA · Every morning",
    deck: "Follow your teams and their news files under the league brief, filed once a day.",
    submit: "Create account",
    altPrompt: "Already have an account?",
    altLabel: "Sign in",
    altTo: "/login",
  },
} as const;

/**
 * A field, set as a line to write on.
 *
 * Underlined rather than boxed. A rounded, filled, bordered input is the one
 * object that would drag the whole page back into being an application, and
 * the underline is what a form printed on paper actually looks like. The rule
 * going spot on focus is the accent doing its declared job -- this is where
 * you are -- rather than a fourth thing it has been asked to mean.
 */
function Field({
  label,
  ...input
}: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="t-wire block pb-2 text-ink-mute">{label}</span>
      <input
        {...input}
        className="t-read block w-full rounded-none border-0 border-b border-rule bg-transparent pb-2 text-ink outline-none transition-colors focus:border-spot"
      />
    </label>
  );
}

/**
 * A message on the line, in the second colour.
 *
 * The old error box was `border-red-300 bg-red-50 text-red-700` -- a fourth
 * colour that exists nowhere else in the design, and one with no dark variant
 * at all, so on the night run it rendered as a light panel on a dark page.
 *
 * On a two-colour press an alarm is not a new hue, it is the spot ink used as
 * one. Errors get the spot rule, notices get the plain one: they are told
 * apart by structure rather than by asking a reader to distinguish two
 * colours.
 */
function Note({ tone, children }: { tone: "error" | "notice"; children: React.ReactNode }) {
  return (
    <p
      role={tone === "error" ? "alert" : "status"}
      className={`t-read border-l-2 pl-4 ${
        tone === "error" ? "border-spot text-ink" : "border-rule text-ink-mute"
      }`}
    >
      {children}
    </p>
  );
}

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
      <div className="pt-12">
        <h1 className="t-display text-[clamp(1.75rem,4vw,2.75rem)] leading-[1.02]">
          The presses are not wired up.
        </h1>
        <p className="t-read pt-4 text-ink-mute">
          Add <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_ANON_KEY</code>{" "}
          to <code>.env</code>, then restart <code>make web</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="pt-12">
      <h1 className="t-display text-[clamp(1.875rem,4.4vw,3rem)] leading-[0.98]">
        {copy.title}
      </h1>

      {copy.standfirst && (
        <p className="t-wire pt-4 text-ink-mute">{copy.standfirst}</p>
      )}
      {copy.deck && (
        <p className="t-read max-w-[42ch] pt-4 text-ink-mute">{copy.deck}</p>
      )}

      <form onSubmit={onSubmit} className="flex flex-col gap-7 pt-10">
        <Field
          label="Email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <Field
          label="Password"
          type="password"
          required
          minLength={6}
          // Tells password managers whether to offer a saved password or
          // generate a new one.
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {error && <Note tone="error">{error}</Note>}
        {notice && <Note tone="notice">{notice}</Note>}

        {/* The one filled object in the whole design, and that is exactly why
            it reads as the action. The accent budget allows it because there
            is precisely one per page and it is what the page is for -- square,
            because nothing else here has a corner radius. */}
        <button
          type="submit"
          disabled={busy}
          className="t-wire w-full cursor-pointer bg-spot px-4 py-4 text-paper transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot disabled:opacity-40"
        >
          {busy ? "Working…" : copy.submit}
        </button>
      </form>

      <p className="t-wire flex flex-wrap items-baseline gap-2 pt-8 text-ink-mute">
        {copy.altPrompt}
        <Link
          to={copy.altTo}
          className="border-b border-spot pb-0.5 text-ink hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
        >
          {copy.altLabel}
        </Link>
      </p>
    </div>
  );
}
