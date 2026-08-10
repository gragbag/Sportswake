import { createClient } from "@supabase/supabase-js";

/**
 * Supabase client, used only for auth -- all story data still comes from our
 * own FastAPI endpoints.
 *
 * Both values are safe in browser code. The anon key is a *publishable* key
 * that identifies the project and grants nothing on its own; access is
 * decided by the JWT the user gets after signing in, and enforced
 * server-side. Do not reach for the service-role key here, ever.
 */
const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

/** False when the keys are missing, so the UI can say so instead of crashing. */
export const authConfigured = Boolean(url && anonKey);

export const supabase = createClient(url ?? "http://localhost", anonKey ?? "public-anon-key", {
  auth: {
    // Keep the session in localStorage and refresh it in the background, so
    // a reload does not sign the user out.
    persistSession: true,
    autoRefreshToken: true,
  },
});
