import { createContext, useContext, useEffect, useState } from "react";

/** Breakpoint at which the sidebar stops being an overlay. Matches Tailwind `md`. */
export const DESKTOP_QUERY = "(min-width: 768px)";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

export interface ShellState {
  isDesktop: boolean;
  /** True when the sidebar is visible (desktop: not collapsed; mobile: drawer open). */
  sidebarVisible: boolean;
  showSidebar: () => void;
  hideSidebar: () => void;
}

export const ShellContext = createContext<ShellState | null>(null);

export function useShell(): ShellState {
  const value = useContext(ShellContext);
  if (!value) throw new Error("useShell must be used inside <AppShell>");
  return value;
}
