import type { ReactNode } from "react";
import { Colophon } from "./Colophon";
import { Masthead } from "./Masthead";

/**
 * The paper every page is printed on.
 *
 * This was two string constants inside BriefPage while the brief was the only
 * route that used newsprint. It is a component now because the ground, the
 * measure and the masthead are one decision -- a page that sets its own column
 * width is a page that will drift from the others by 20px and nobody will know
 * which one is right.
 *
 * No sticky bar, and deliberately so. The app shell floats a backdrop-blurred
 * header over its content; doing that here would undo the argument the whole
 * design makes, that depth comes from hairlines and paper tone and never from
 * a translucent panel. The masthead scrolls away like the top of a page.
 *
 * `generatedAt` is the dateline of what is printed beneath it. Pages that are
 * not an edition -- sign-in, settings -- pass nothing and get today's date,
 * which is what a masthead carries when the page under it is not news.
 */
export function PressShell({
  generatedAt = null,
  stale,
  children,
}: {
  generatedAt?: string | null;
  stale?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="min-h-dvh bg-paper text-ink">
      <div className="mx-auto w-full max-w-[1180px] px-5 pb-24 lg:px-12">
        <Masthead generatedAt={generatedAt} stale={stale} />
        {children}
        <Colophon />
      </div>
    </div>
  );
}
