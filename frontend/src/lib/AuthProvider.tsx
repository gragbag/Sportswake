import type { Session } from "@supabase/supabase-js";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { AuthContext, type AuthValue } from "./auth";
import { supabase } from "./supabase";

/**
 * Holds the Supabase session for the whole app.
 *
 * This file exports ONLY a component on purpose -- mixing components and
 * plain functions in one module breaks React Fast Refresh, which is why the
 * context, the hook, and apiFetch live in auth.ts next door.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Two things happen here, and both are needed. getSession() restores an
    // existing login from localStorage on a cold page load; onAuthStateChange
    // keeps us in sync afterwards -- sign-in, sign-out, and the silent token
    // refresh that happens roughly hourly.
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setLoading(false);
    });

    return () => sub.subscription.unsubscribe();
  }, []);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
  }, []);

  // Memoised so consumers do not re-render on every provider render.
  const value = useMemo<AuthValue>(
    () => ({
      session,
      loading,
      email: session?.user.email ?? null,
      signOut,
    }),
    [session, loading, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
