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

export type Profile = {
  user_id: string;
  email: string | null;
  /** Null when they have never chosen one; `handle` is the derived fallback. */
  username: string | null;
  /** What actually renders: chosen username, or the derived handle. */
  handle: string;
  /** ISO timestamp, or null when no cooldown is running. */
  can_change_at: string | null;
  hide_comment_history: boolean;
};

export type Comment = {
  id: string;
  /** Author's Supabase user id -- used only to mark a comment as your own. */
  user_id: string;
  /** Display name, resolved server-side so every surface agrees. */
  author: string;
  body: string;
  created_at: string;
  edited_at: string | null;
  /** Net score: upvotes minus downvotes. */
  score: number;
  /** The viewer's own vote: 1, -1, or 0 when they have not voted. */
  my_vote: number;
};

/** A comment as listed on a user's profile, where the story is the context. */
export type ProfileComment = Comment & {
  story_id: string;
  story_title: string;
};

export type PublicProfile = {
  user_id: string;
  handle: string;
  joined_at: string | null;
  is_self: boolean;
  history_hidden: boolean;
  comments: ProfileComment[];
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
