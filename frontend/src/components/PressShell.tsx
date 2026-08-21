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
 * The masthead takes nothing. It used to take the edition's filed time, which
 * meant every page had to have an opinion about a dateline it did not own --
 * and the pages that had no edition passed nothing and got today's clock.
 * A dateline belongs to an edition, so it is printed by the edition.
 */
export function PressShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-paper text-ink">
      <div className="mx-auto w-full max-w-[1180px] px-5 pb-24 lg:px-12">
        <Masthead />
        {children}
        <Colophon />
      </div>
    </div>
  );
}
