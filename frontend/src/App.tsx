import { Outlet, Route, Routes } from "react-router-dom";
import { AuthPage } from "./components/AuthPage";
import { BriefPage } from "./components/BriefPage";
import { FavoritesPage } from "./components/FavoritesPage";
import { Feed } from "./components/Feed";
import { PressShell } from "./components/PressShell";
import { SettingsPage } from "./components/SettingsPage";
import { StoryPage } from "./components/StoryPage";
import { UserPage } from "./components/UserPage";

/**
 * Paper, as a layout route.
 *
 * There is one shell now. The app shell this replaced capped content at
 * max-w-5xl and floated a backdrop-blurred bar over it, which is the exact
 * thing the design says depth must never come from -- and it carried a second
 * copy of the account nav and a second theme control, so the same two
 * decisions were made twice and drifted. Its header also overflowed a 390px
 * viewport by 25px, which no amount of restyling was going to fix.
 *
 * Listing a page here is how it joins the paper.
 */
function PressLayout() {
  return (
    <PressShell>
      <Outlet />
    </PressShell>
  );
}

export default function App() {
  // The brief is the one route outside the layout, because it is the only page
  // that has a dateline to put in its masthead -- it passes the filed time of
  // the edition on the page, where every other page carries today's date.
  return (
    <Routes>
      <Route path="/" element={<BriefPage />} />

      <Route element={<PressLayout />}>
        {/* The feed that predates the brief, kept as a browsing surface:
            every multi-outlet story, filterable by team and category. The two
            filters compose; each combination is one Feed. */}
        <Route path="/stories" element={<Feed />} />
        <Route path="/stories/c/:category" element={<Feed />} />
        <Route path="/stories/t/:team" element={<Feed />} />
        <Route path="/stories/t/:team/c/:category" element={<Feed />} />

        {/* Signing up is the second most important page in the product -- it
            is where a reader becomes a subscriber -- so it is printed on the
            same paper as the front page, next to the front page. */}
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/signup" element={<AuthPage mode="signup" />} />

        {/* The coverage timeline is the surface the design doc calls the
            differentiator, so the story page gets the full measure. */}
        <Route path="/story/:storyId" element={<StoryPage />} />

        <Route path="/favorites" element={<FavoritesPage />} />
        <Route path="/u/:handle" element={<UserPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
