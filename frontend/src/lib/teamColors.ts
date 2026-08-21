/**
 * Club colour, for charts and nothing else.
 *
 * A previous version of this file was deleted when the app went to one
 * two-colour system, on the argument that thirty saturated brand palettes
 * competing down a reading page turn a brief into a scoreboard. That argument
 * still holds for reading surfaces: the feed, the story page and the brief
 * itself identify a club by its three-letter code in mono, and they keep doing
 * that. This file exists for the one place colour does real work -- a chart,
 * where a fill identifies a series without a legend.
 *
 * THESE ARE NOT THE BRAND HEXES. The real primaries do not survive contact
 * with newsprint: measured against the paper (#e4e1d6) the old file's values
 * failed on three counts at once -- the yellows sat at OKLCH L 0.85 where the
 * band tops out at 0.77, Brooklyn and San Antonio came in at chroma 0.005 and
 * read as flat grey, and twelve of thirty fell under 3:1 contrast. Two pairs
 * were literally the same hex: Atlanta and Portland, and three of Chicago,
 * Houston and Toronto.
 *
 * So each club keeps its HUE -- that is what makes a colour read as theirs --
 * and lightness and chroma are snapped into the band that passes, separately
 * for each run, with same-hue families fanned apart in both value and hue.
 * Verified with the data-viz validator: lightness band, chroma floor and
 * contrast all PASS against both #e4e1d6 and #1a1b18.
 *
 * WHAT DOES NOT PASS, KNOWINGLY: colourblind separation between clubs that
 * share a hue. The league has four reds and six blues; no amount of tuning
 * separates Chicago from Houston while both stay recognisably crimson. That
 * is allowed only where colour is not carrying identity on its own, so every
 * mark drawn with these is directly labelled with its club code, and the
 * label is the identity. Colour is reinforcement. Never draw one of these
 * without the code beside it.
 */

/** [day run, night run]. */
type Pair = readonly [string, string];

const TEAM_COLORS: Record<string, Pair> = {
  ATL: ["#c34129", "#e05d43"],
  BOS: ["#186100", "#418227"],
  // Brooklyn and San Antonio are deliberate exceptions to the chroma floor.
  // Their brands are black and silver -- there is no hue to preserve, and
  // inventing one gave Brooklyn an indigo it has never worn. A neutral that
  // the label identifies beats a colour that is simply wrong; they are set
  // warm and cool respectively so the two are not each other.
  BKN: ["#4b4a46", "#8d8a80"],
  CHA: ["#007698", "#0092b0"],
  CHI: ["#9b1041", "#c13c60"],
  CLE: ["#a92f54", "#cb4f70"],
  DAL: ["#2670c5", "#4f8cd7"],
  DEN: ["#957600", "#ad8f00"],
  DET: ["#b02a34", "#d24c4f"],
  GSW: ["#1e5ab0", "#477ac7"],
  HOU: ["#a21941", "#c7415e"],
  IND: ["#843600", "#a95900"],
  LAC: ["#b73232", "#d7514d"],
  LAL: ["#7649a9", "#9366c9"],
  MEM: ["#4563c0", "#6381d4"],
  MIA: ["#940543", "#bb3863"],
  MIL: ["#009359", "#32a975"],
  MIN: ["#0064ad", "#2583c4"],
  NOP: ["#8b5900", "#a47800"],
  NYK: ["#a83e00", "#c95c00"],
  OKC: ["#005894", "#007bb5"],
  ORL: ["#006bb9", "#2e88d5"],
  PHI: ["#4176d0", "#5b8fe7"],
  PHX: ["#5235a5", "#7059cb"],
  POR: ["#c94926", "#e56240"],
  SAC: ["#9b58b3", "#b274c8"],
  SAS: ["#5d6b73", "#93a2ab"],
  TOR: ["#a92140", "#cc465c"],
  UTA: ["#00539b", "#1176b6"],
  WAS: ["#bd3931", "#dc564b"],
};

/** The rule ink, for anything with no club of its own -- "others", scopes. */
const UNCLAIMED: Pair = ["#a9a596", "#5b5d55"];

/**
 * The two runs of a club's colour, as CSS custom properties.
 *
 * Returned as a style object rather than a single string because which one
 * applies is the stylesheet's decision, not this module's: the theme has three
 * states and only CSS can see all of them. `.team-fill` in tokens.css picks.
 */
export function teamInk(code: string | null | undefined): {
  "--team-day": string;
  "--team-night": string;
} {
  const [day, night] = (code && TEAM_COLORS[code]) || UNCLAIMED;
  return { "--team-day": day, "--team-night": night };
}
