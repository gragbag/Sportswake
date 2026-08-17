export type Theme = "light" | "dark" | "system";

const KEY = "sportswake:theme";

/**
 * Apply a theme choice to the document.
 *
 * "system" REMOVES the attribute rather than setting it to anything, which is
 * the whole trick: with no attribute the stylesheet falls through to
 * prefers-color-scheme, so following the OS needs no JavaScript at all and
 * keeps working if this module never runs.
 */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

export function readTheme(): Theme {
  const saved = localStorage.getItem(KEY);
  return saved === "light" || saved === "dark" ? saved : "system";
}

export function saveTheme(theme: Theme): void {
  if (theme === "system") localStorage.removeItem(KEY);
  else localStorage.setItem(KEY, theme);
  applyTheme(theme);
}
