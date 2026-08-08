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
