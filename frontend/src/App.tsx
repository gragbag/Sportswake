import { Link, Route, Routes } from "react-router-dom";
import { Feed } from "./components/Feed";
import { StoryPage } from "./components/StoryPage";

export default function App() {
  return (
    <div className="min-h-screen bg-white font-sans dark:bg-ink-900">
      {/* max-w + mx-auto caps the line length and centres what is left, so on
          a wide monitor the outer whitespace is set by the window, not by
          px-12 -- it will always dwarf the column gutter. Uncapping this is
          the only way to make the three gaps truly equal, at the cost of a
          much wider text column. */}
      <div className="mx-auto max-w-6xl px-6 py-12 lg:px-12">
        <header className="mb-8">
          <Link to="/" className="inline-block">
            <h1 className="text-2xl font-semibold text-ink-900 dark:text-white">
              Presswake
            </h1>
          </Link>
          <p className="mt-1 text-sm text-ink-500 dark:text-white/50">
            How every outlet covered the same story &mdash; who published, when,
            and who didn&rsquo;t.
          </p>
        </header>

        <Routes>
          <Route path="/" element={<Feed />} />
          <Route path="/story/:storyId" element={<StoryPage />} />
        </Routes>
      </div>
    </div>
  );
}
