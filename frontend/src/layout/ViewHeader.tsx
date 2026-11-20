import type { ReactNode } from "react";
import { IconButton } from "../ui/Button";
import { MenuIcon, SidebarIcon } from "../ui/icons";
import { useShell } from "./shell";

/** Top bar of every view: sidebar toggle when hidden, title, view actions. */
export function ViewHeader({ title, actions }: { title: ReactNode; actions?: ReactNode }) {
  const { isDesktop, sidebarVisible, showSidebar } = useShell();

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3 md:px-4">
      {!sidebarVisible && (
        <IconButton
          label={isDesktop ? "Show sidebar" : "Open navigation"}
          onClick={showSidebar}
        >
          {isDesktop ? <SidebarIcon /> : <MenuIcon />}
        </IconButton>
      )}
      <h1 className="min-w-0 flex-1 truncate text-control font-medium text-ink">{title}</h1>
      {actions && <div className="flex shrink-0 items-center gap-1">{actions}</div>}
    </header>
  );
}
