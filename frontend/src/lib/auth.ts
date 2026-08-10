import type { Session } from "@supabase/supabase-js";
import { createContext, useContext } from "react";
import { supabase } from "./supabase";

export type AuthValue = {
  session: Session | null;
  /** True while the initial session is still being restored from storage. */
  loading: boolean;
  email: string | null;
  signOut: () => Promise<void>;
};

export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  // Throwing beats returning null: this fires the moment a component is
  // rendered outside the provider, rather than as a mystery null later.
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/**
 * fetch() with the user's access token attached when signed in.
 *
 * Read the token at call time rather than closing over it -- supabase-js
 * refreshes it in the background, and a captured token goes stale.
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  return fetch(path, {
    ...init,
    headers: {
      ...init.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}
