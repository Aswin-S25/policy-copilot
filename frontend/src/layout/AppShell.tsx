import { useCallback, useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { ServiceBanner } from "./ServiceBanner";
import { Sidebar } from "./Sidebar";
import { DESKTOP_QUERY, ShellContext, useMediaQuery, type ShellState } from "./shell";

/**
 * Application frame: sidebar on the canvas, the active view on an inset
 * surface. On desktop the sidebar can be collapsed; below 768px it becomes
 * an overlay drawer that closes on navigation, Escape or backdrop click.
 */
export function AppShell() {
  const isDesktop = useMediaQuery(DESKTOP_QUERY);
  const [desktopCollapsed, setDesktopCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  // A navigation from the drawer should reveal the destination.
  useEffect(() => setMobileOpen(false), [location.pathname]);

  // Ctrl/Cmd + Shift + O: new chat (the convention ChatGPT users already know).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "o") {
        event.preventDefault();
        navigate("/");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  useEffect(() => {
    if (isDesktop || !mobileOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isDesktop, mobileOpen]);

  const showSidebar = useCallback(
    () => (isDesktop ? setDesktopCollapsed(false) : setMobileOpen(true)),
    [isDesktop],
  );
  const hideSidebar = useCallback(
    () => (isDesktop ? setDesktopCollapsed(true) : setMobileOpen(false)),
    [isDesktop],
  );

  const sidebarVisible = isDesktop ? !desktopCollapsed : mobileOpen;

  const shell = useMemo<ShellState>(
    () => ({ isDesktop, sidebarVisible, showSidebar, hideSidebar }),
    [isDesktop, sidebarVisible, showSidebar, hideSidebar],
  );

  return (
    <ShellContext.Provider value={shell}>
      <a
        href="#main"
        className={
          "sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-control " +
          "focus:bg-surface focus:px-3 focus:py-2 focus:text-control focus:font-medium focus:shadow-overlay"
        }
      >
        Skip to main content
      </a>
      <div className="flex h-full overflow-hidden bg-canvas">
        {isDesktop ? (
          sidebarVisible && (
            <div className="w-[264px] shrink-0">
              <Sidebar />
            </div>
          )
        ) : (
          <>
            <div
              aria-hidden="true"
              onClick={hideSidebar}
              className={
                "fixed inset-0 z-30 bg-ink/25 transition-opacity duration-200 " +
                (mobileOpen ? "opacity-100" : "pointer-events-none opacity-0")
              }
            />
            <div
              // A dialog only while open; closed, it is inert and hidden from assistive tech.
              role={mobileOpen ? "dialog" : undefined}
              aria-modal={mobileOpen || undefined}
              aria-label={mobileOpen ? "Navigation" : undefined}
              aria-hidden={!mobileOpen || undefined}
              inert={!mobileOpen}
              className={
                "fixed inset-y-0 left-0 z-40 w-[288px] max-w-[85vw] bg-canvas " +
                "transition-transform duration-200 ease-out-soft " +
                // Shadow only when open: off-screen it would bleed onto the left edge.
                (mobileOpen ? "translate-x-0 shadow-overlay" : "-translate-x-full")
              }
            >
              <Sidebar />
            </div>
          </>
        )}

        <main
          id="main"
          tabIndex={-1}
          className={
            "focus:outline-none " +
            "flex min-w-0 flex-1 flex-col overflow-hidden bg-surface " +
            "md:my-2 md:mr-2 md:rounded-panel md:border md:border-line " +
            (isDesktop && !sidebarVisible ? "md:ml-2" : "")
          }
        >
          <ServiceBanner />
          <Outlet />
        </main>
      </div>
    </ShellContext.Provider>
  );
}
