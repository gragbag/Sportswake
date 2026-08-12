export type Story = {
  id: string;
  /** Seed-article headline. Fallback when no summary has been generated. */
  title: string;
  /** AI-generated headline, or null if the story is unsummarized. */
  summary_title: string | null;
  /** One AI-generated line on why it matters; null when unsummarized. */
  summary_subhead: string | null;
  article_count: number;
  outlet_count: number;
  first_at: string;
  last_at: string;
  span_hours: number;
  /** Outlet names in order of first publication -- index 0 broke the story. */
  outlets: string[];
  /** Article counts bucketed across the story's lifespan, for the sparkline. */
  buckets: number[];
};

export type Comment = {
  id: string;
  /** Author's Supabase user id. Not their email -- that is personal data and
   *  does not belong in a public payload. Display names would replace this. */
  user_id: string;
  body: string;
  created_at: string;
  edited_at: string | null;
};

/** One member article of a story, as returned by /api/stories/{id}. */
export type StoryArticle = {
  outlet: string;
  headline: string;
  url: string;
  published_at: string;
};

/**
 * A single story with every member article. Distinct from Story: the feed
 * gets outlet names and sparkline buckets, the page gets the real rows.
 */
export type StoryDetail = {
  id: string;
  title: string;
  summary_title: string | null;
  summary_subhead: string | null;
  summary_bullets: string[] | null;
  summary_people: string[] | null;
  summary_model: string | null;
  summarized_at: string | null;
  article_count: number;
  outlet_count: number;
  first_at: string;
  last_at: string;
  span_hours: number;
  /** Chronological, oldest first. */
  articles: StoryArticle[];
};
