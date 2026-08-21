import { AuthForm } from "./AuthForm";
import { LatestPlate } from "./LatestPlate";

/**
 * Sign in / get started, as a spread.
 *
 * The form on the left and the day's actual front page on the right, at the
 * brief's own 46/46 proportion. Two reasons, and the second one is the real
 * one: a 30rem form alone on an 1180px measure looks like a page that lost
 * its other half, and a reader deciding whether to hand over an email is
 * entitled to see today's paper while they decide.
 */
export function AuthPage({ mode }: { mode: "login" | "signup" }) {
  return (
    <div className="grid grid-cols-1 gap-x-[8%] gap-y-4 md:grid-cols-[repeat(2,46%)] md:justify-between">
      <AuthForm mode={mode} />
      <LatestPlate />
    </div>
  );
}
