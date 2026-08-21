/**
 * One story a section drew on, collapsed across its coverage.
 *
 * A story, not an article: a big one carries sixteen near-identical
 * headlines, and listing all sixteen reads as a bug. The outlet count is the
 * corroboration signal and the lead link is the way in.
 */
export type BriefStory = {
  id: string;
  headline: string;
  outlet_count: number;
  first_at: string;
  lead_outlet: string;
  lead_url: string;
  outlets: string[];
  /** Club codes, best-ranked first. Empty when nothing could be placed. */
  teams: string[];
};

/**
 * One pre-written piece of a brief. Written per team, never per user, and
 * assembled at read time -- so this is what the server looked up, not what
 * it generated for you.
 */
export type BriefSection = {
  scope: "league" | "team";
  /** Null on the league section. */
  team: string | null;
  team_name: string | null;
  body_md: string;
  word_count: number;
  /** True when the trailing-percentile gate lifted this section's budget. */
  is_major: boolean;
  /** In the order the section used them, so the page matches the prose. */
  stories: BriefStory[];
};

/** A slot that exists for this date, for the collapsed cards below the fold. */
export type BriefSlot = {
  slot: "morning" | "midday" | "night";
  generated_at: string;
  word_count: number;
  first_line: string;
};

export type Brief = {
  /** Null when nothing has ever been generated. */
  slot: "morning" | "midday" | "night" | null;
  slot_date?: string;
  generated_at?: string | null;
  /** True when the served slot is not today's -- say so rather than imply. */
  is_stale: boolean;
  sections: BriefSection[];
  available_slots: BriefSlot[];
  following: string[];
  /** Followed teams whose section was dropped as redundant or over the cap. */
  omitted_team_count: number;
  /**
   * Every edition of the day, keyed by slot, each in this same shape.
   * Present only when the request asked for all_slots=1 -- the initial page
   * load does, so sibling editions arrive with the first response instead
   * of as background fetches.
   */
  editions?: Record<string, Brief>;
};

export type Category = { slug: string; label: string };

/** A tab: a category plus how many feed-eligible stories it holds. */
export type CategoryTab = Category & { count: number };

/** A team tag on a story: LAL / Los Angeles Lakers. */
export type Team = { code: string; name: string };

/**
 * A selector entry. `kind` is 'team' for the 30 clubs, 'conference' for
 * EAST/WEST, 'league' for LEAGUE -- the dropdown groups on it.
 */
export type TeamOption = Team & { kind: string; count: number };

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
  /** Ordered by rank -- element 0 is whose story it mostly is. Empty is normal. */
  teams: Team[];
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
  /** Rank-ordered, same shape as Story.teams. Empty is normal. */
  teams: Team[];
  /** Chronological, oldest first. */
  articles: StoryArticle[];
};
