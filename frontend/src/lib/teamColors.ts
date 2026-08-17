/**
 * One colour per club, used as a thin rule beside a team's section and
 * nothing else.
 *
 * Deliberately restrained: the design direction asks for team colour as an
 * accent on team sections, not as a theme. Thirty saturated brand palettes
 * competing down a reading page would turn a brief into a scoreboard, so a
 * team gets four pixels of its own colour and the page keeps one accent.
 *
 * Each value is the club's primary, nudged where necessary to stay legible
 * as a small mark on both a white and a near-black ground -- several NBA
 * primaries are navy or black, which vanish in dark mode.
 */
export const TEAM_COLORS: Record<string, string> = {
  ATL: "#e03a3e",
  BOS: "#1c8a54",
  BKN: "#8a8d8f",
  CHA: "#00a2b3",
  CHI: "#ce1141",
  CLE: "#b8385a",
  DAL: "#0f7bc4",
  DEN: "#fec524",
  DET: "#d95b6a",
  GSW: "#fdb927",
  HOU: "#ce1141",
  IND: "#fdbb30",
  LAC: "#d33b4d",
  LAL: "#7c4bbd",
  MEM: "#5d76a9",
  MIA: "#c8446b",
  MIL: "#3d8a63",
  MIN: "#42a5d8",
  NOP: "#a58a5c",
  NYK: "#f58426",
  OKC: "#2f7fd0",
  ORL: "#3f7fd0",
  PHI: "#3a7fd0",
  PHX: "#9b6bd6",
  POR: "#e03a3e",
  SAC: "#8f6bd6",
  SAS: "#a4a9ad",
  TOR: "#ce1141",
  UTA: "#4a8f6b",
  WAS: "#4f7fc4",
};

/** Falls back to the page accent for the league scope and anything unknown. */
export function teamColor(code: string | null | undefined): string {
  if (!code) return "var(--color-accent)";
  return TEAM_COLORS[code] ?? "var(--color-accent)";
}
