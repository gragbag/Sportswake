import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiFetch, useAuth } from "./auth";
import { FavoritesContext, type FavoritesValue } from "./favorites";

/**
 * Holds the set of favorited story ids for the whole app.
 *
 * One request on sign-in rather than one per card: a 24-card feed would
 * otherwise fire 24 "is this favorited" calls.
 */
export function FavoritesProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const [ids, setIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!session) {
      // Signing out must clear the set, or the next user briefly sees the
      // previous user's stars.
      setIds(new Set());
      return;
    }
    apiFetch("/api/favorites/ids")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((list: string[]) => setIds(new Set(list)))
      .catch(() => setIds(new Set()));
  }, [session]);

  const toggle = useCallback(
    async (storyId: string) => {
      const wasFavorite = ids.has(storyId);

      // Optimistic: flip immediately so the star does not lag a round trip.
      setIds((prev) => {
        const next = new Set(prev);
        if (wasFavorite) next.delete(storyId);
        else next.add(storyId);
        return next;
      });

      try {
        const res = await apiFetch(`/api/favorites/${storyId}`, {
          method: wasFavorite ? "DELETE" : "PUT",
        });
        if (!res.ok) throw new Error(String(res.status));
      } catch {
        // Roll back to the truth we last knew, so a failed request does not
        // leave the UI claiming something the server never accepted.
        setIds((prev) => {
          const next = new Set(prev);
          if (wasFavorite) next.add(storyId);
          else next.delete(storyId);
          return next;
        });
      }
    },
    [ids],
  );

  const value = useMemo<FavoritesValue>(
    () => ({ ids, isFavorite: (id) => ids.has(id), toggle }),
    [ids, toggle],
  );

  return <FavoritesContext.Provider value={value}>{children}</FavoritesContext.Provider>;
}
