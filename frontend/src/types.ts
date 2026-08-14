export type Category = { slug: string; label: string };

/** A tab: a category plus how many feed-eligible stories it holds. */
export type CategoryTab = Category & { count: number };

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
  /** Ordered by rank -- element 0 is the primary label. Empty is normal. */
  categories: Category[];
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
  /** Null for a top-level comment. */
  parent_id: string | null;
  /** 0 at top level; the API caps how deep a reply may go. */
  depth: number;
  /** 'visible' | 'deleted' | 'removed'. The last two are tombstones and
   *  arrive with author and body null. */
  status: string;
  /** Author's Supabase user id -- used only to mark a comment as your own. */
  user_id: string;
  /** Resolved server-side so every surface agrees. Null on a tombstone. */
  author: string | null;
  /** Null on a tombstone -- the row keeps its text, the API stops serving it. */
  body: string | null;
  created_at: string;
  edited_at: string | null;
  /** Net score: upvotes minus downvotes. */
  score: number;
  /** The viewer's own vote: 1, -1, or 0 when they have not voted. */
  my_vote: number;
};

/** A comment with its replies attached, built client-side from the flat list. */
export type CommentNodeData = Comment & { replies: CommentNodeData[] };

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
  /** Rank-ordered, same shape as Story.categories. Empty is normal. */
  categories: Category[];
  /** Chronological, oldest first. */
  articles: StoryArticle[];
};
