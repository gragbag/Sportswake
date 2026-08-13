import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiFetch, useAuth } from "../lib/auth";
import type { Profile } from "../types";

/** Mirrors the server's rule. The server is still the one that enforces it. */
const USERNAME_RE = /^[a-zA-Z0-9_]{3,20}$/;

export function SettingsPage() {
  const { session, loading: authLoading, email } = useAuth();

  const [profile, setProfile] = useState<Profile | null>(null);
  const [draft, setDraft] = useState("");
  const [available, setAvailable] = useState<null | { ok: boolean; why: string | null }>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!session) return;
    apiFetch("/api/profile")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((p: Profile) => {
        setProfile(p);
        setDraft(p.username ?? "");
      })
      .catch(() => setError("Could not load your profile"));
  }, [session]);

  // Advisory availability check, debounced. Never gates submit -- the unique
  // index decides, and this can lose a race.
  useEffect(() => {
    const name = draft.trim();
    if (!name || name === profile?.username || !USERNAME_RE.test(name)) {
      setAvailable(null);
      return;
    }
    const timer = setTimeout(() => {
      fetch(`/api/username-available?username=${encodeURIComponent(name)}`)
        .then((r) => r.json())
        .then((d) => setAvailable({ ok: d.available, why: d.reason }))
        .catch(() => setAvailable(null));
    }, 350);
    return () => clearTimeout(timer);
  }, [draft, profile?.username]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    setBusy(true);
    try {
      const res = await apiFetch("/api/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: draft.trim() }),
      });
      if (!res.ok) {
        const detail = await res.json().then((d) => d.detail).catch(() => null);
        throw new Error(detail ?? `Could not save (HTTP ${res.status})`);
      }
      const updated = await res.json();
      setProfile((p) => (p ? { ...p, ...updated } : p));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  if (authLoading) {
    return <p className="text-sm text-ink-500 dark:text-white/50">Loading&hellip;</p>;
  }

  if (!session) {
    return (
      <p className="text-sm text-ink-500 dark:text-white/50">
        <Link to="/login" className="underline">
          Sign in
        </Link>{" "}
        to manage your account.
      </p>
    );
  }

  // Present only while the cooldown is still running.
  const lockedUntil =
    profile?.can_change_at && new Date(profile.can_change_at) > new Date()
      ? new Date(profile.can_change_at)
      : null;

  return (
    <div className="max-w-md">
      <h1 className="text-xl font-semibold text-ink-900 dark:text-white">Settings</h1>

      <dl className="mt-6 space-y-3 text-sm">
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-ink-500 dark:text-white/40">
            Email
          </dt>
          <dd className="text-ink-900 dark:text-white/90">{email}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-ink-500 dark:text-white/40">
            Shown on your comments
          </dt>
          <dd className="text-ink-900 dark:text-white/90">
            {profile?.handle ?? "…"}
            {profile && !profile.username && (
              <span className="ml-2 text-[11px] text-ink-500 dark:text-white/40">
                assigned &mdash; pick your own below
              </span>
            )}
          </dd>
        </div>
      </dl>

      <form onSubmit={onSubmit} className="mt-8">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wide text-ink-500 dark:text-white/40">
            Username
          </span>
          <input
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setSaved(false);
            }}
            disabled={Boolean(lockedUntil)}
            placeholder="3-20 characters, letters, numbers, underscore"
            className="rounded border border-ink-200 bg-white px-3 py-2 text-sm text-ink-900
                       outline-none focus:border-ink-500 disabled:opacity-50
                       dark:border-white/10 dark:bg-white/5 dark:text-white"
          />
        </label>

        {lockedUntil ? (
          <p className="mt-2 text-[11px] text-ink-500 dark:text-white/40">
            You changed your username recently. You can change it again after{" "}
            {lockedUntil.toLocaleDateString()}.
          </p>
        ) : (
          <p className="mt-2 text-[11px] text-ink-500 dark:text-white/40">
            Changing your username frees the old one for someone else, so this is
            limited to once a month.
          </p>
        )}

        {available && (
          <p
            className={`mt-1 text-[11px] ${
              available.ok ? "text-ink-500 dark:text-white/50" : "text-red-600"
            }`}
          >
            {available.ok ? `${draft.trim()} is available` : `Not available: ${available.why}`}
          </p>
        )}

        <div className="mt-3 flex items-center gap-3">
          <button
            type="submit"
            disabled={busy || Boolean(lockedUntil) || !draft.trim() || draft.trim() === profile?.username}
            className="rounded bg-ink-900 px-3 py-1.5 text-xs font-medium text-white
                       disabled:opacity-40 dark:bg-white dark:text-ink-900"
          >
            {busy ? "Saving…" : "Save"}
          </button>
          {saved && (
            <span className="text-[11px] text-ink-500 dark:text-white/50">
              Saved. Your name is updated on every comment you have posted.
            </span>
          )}
          {error && <span className="text-[11px] text-red-600">{error}</span>}
        </div>
      </form>
    </div>
  );
}
