import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

/** Seconds left until `until` (epoch ms), ticking each second; 0 once passed. */
export function useCountdown(until: number | undefined): number {
  const remaining = () => (until ? Math.max(0, Math.ceil((until - Date.now()) / 1000)) : 0);
  const [seconds, setSeconds] = useState(remaining);

  useEffect(() => {
    setSeconds(remaining());
    if (!until || until <= Date.now()) return;
    const timer = window.setInterval(() => {
      const left = remaining();
      setSeconds(left);
      if (left === 0) window.clearInterval(timer);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [until]); // `remaining` reads only `until`

  return seconds;
}

/**
 * Keeps a scroll container at the bottom while content grows, unless the
 * reader has scrolled up to read something; then it leaves them there.
 */
export function useStickToBottom(ref: RefObject<HTMLElement | null>, contentKey: unknown) {
  const pinned = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => {
      pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 96;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [ref]);

  useLayoutEffect(() => {
    const el = ref.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [ref, contentKey]);

  /** Re-pin, e.g. when the user sends a question. */
  return useCallback(() => {
    pinned.current = true;
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [ref]);
}
