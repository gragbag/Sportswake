import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiFetch, useAuth } from "../lib/auth";
import type { Profile } from "../types";
import { TeamPicker } from "./TeamPicker";
import { SlugRule } from "./press";

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

  async function setPrivacy(hide: boolean) {
    // Optimistic, and reverted on failure -- a checkbox that silently
    // disagrees with the server is worse than one that snaps back.
    setProfile((p) => (p ? { ...p, hide_comment_history: hide } : p));
    try {
      const res = await apiFetch("/api/profile/privacy", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hide_comment_history: hide }),
      });
      if (!res.ok) throw new Error(String(res.status));
    } catch {
      setProfile((p) => (p ? { ...p, hide_comment_history: !hide } : p));
      setError("Could not save that setting");
    }
  }

  if (authLoading) {
    return <p className="t-wire pt-8 text-ink-mute">Loading&hellip;</p>;
  }

  if (!session) {
    return (
      <p className="t-read pt-8 text-ink-mute">
        <Link
          to="/login"
          className="border-b border-spot pb-0.5 text-ink hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
        >
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
    <div className="max-w-[42rem] pt-12">
      <h1 className="t-display text-[clamp(1.875rem,4.4vw,3rem)] leading-[0.98]">
        Settings.
      </h1>

      {/* First, because it is the only setting that changes what you read. */}
      <section className="pt-10">
        <SlugRule label="Your teams" />
        <div className="pt-6">
          <TeamPicker />
        </div>
      </section>

      <dl className="pt-10">
        <div>
          <dt className="t-wire text-ink-mute">Email</dt>
          <dd className="t-read pt-1 text-ink">{email}</dd>
        </div>
        <div>
          <dt className="t-wire pt-5 text-ink-mute">Shown on your comments</dt>
          <dd className="t-read pt-1 text-ink">
            {profile?.handle ?? "…"}
            {profile && !profile.username && (
              <span className="t-wire ml-2 text-ink-mute">
                assigned &mdash; pick your own below
              </span>
            )}
          </dd>
        </div>
      </dl>

      <form onSubmit={onSubmit} className="pt-10">
        <label className="block">
          <span className="t-wire block pb-2 text-ink-mute">Username</span>
          <input
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setSaved(false);
            }}
            disabled={Boolean(lockedUntil)}
            placeholder="3-20 characters, letters, numbers, underscore"
            className="t-read block w-full rounded-none border-0 border-b border-rule bg-transparent pb-2 text-ink outline-none transition-colors focus:border-spot disabled:opacity-50"
          />
        </label>

        {lockedUntil ? (
          <p className="t-wire pt-3 text-ink-mute">
            You changed your username recently. You can change it again after{" "}
            {lockedUntil.toLocaleDateString()}.
          </p>
        ) : (
          <p className="t-wire pt-3 text-ink-mute">
            Changing your username frees the old one for someone else, so this is
            limited to once a month.
          </p>
        )}

        {available && (
          <p
            className={`t-wire pt-2 ${available.ok ? "text-ink-mute" : "text-spot"}`}
          >
            {available.ok ? `${draft.trim()} is available` : `Not available: ${available.why}`}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-4 pt-6">
          <button
            type="submit"
            disabled={busy || Boolean(lockedUntil) || !draft.trim() || draft.trim() === profile?.username}
            className="t-wire cursor-pointer bg-spot px-5 py-3 text-paper transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {busy ? "Saving…" : "Save"}
          </button>
          {saved && (
            <span className="t-wire text-ink-mute">
              Saved. Your name is updated on every comment you have posted.
            </span>
          )}
          {error && <span className="t-wire text-spot">{error}</span>}
        </div>
      </form>

      <section className="pt-12">
        <SlugRule label="Privacy" />

        <label className="flex items-start gap-3 pt-6">
          <input
            type="checkbox"
            checked={profile?.hide_comment_history ?? false}
            onChange={(e) => void setPrivacy(e.target.checked)}
            className="mt-1 accent-spot"
          />
          <span className="t-read text-ink">
            Hide my comment history
            <span className="t-wire mt-1.5 block text-ink-mute">
              Your profile stops listing your comments. They stay visible on the
              stories where you posted them &mdash; hiding is not deleting.
            </span>
          </span>
        </label>

        {profile && (
          <Link
            to={`/u/${profile.username ?? profile.user_id}`}
            className="t-wire mt-6 inline-block border-b border-spot pb-1 text-ink hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spot"
          >
            View my public profile
          </Link>
        )}
      </section>
    </div>
  );
}
