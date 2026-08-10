import { createContext, useContext } from "react";

export type FavoritesValue = {
  /** Story ids the signed-in user has saved. Empty when signed out. */
  ids: Set<string>;
  isFavorite: (storyId: string) => boolean;
  toggle: (storyId: string) => Promise<void>;
};

export const FavoritesContext = createContext<FavoritesValue | null>(null);

export function useFavorites(): FavoritesValue {
  const ctx = useContext(FavoritesContext);
  if (!ctx) throw new Error("useFavorites must be used inside <FavoritesProvider>");
  return ctx;
}
