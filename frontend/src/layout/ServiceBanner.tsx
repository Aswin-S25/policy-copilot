import { useEffect, useState } from "react";
import { getServiceState, type ServiceState } from "../api/health";
import { useWakeState } from "../api/wake";
import { Notice } from "../ui/feedback";

/** Re-check quickly while degraded, rarely while healthy. */
const RECHECK_DEGRADED_MS = 15_000;
const RECHECK_READY_MS = 120_000;

const MESSAGES: Record<Exclude<ServiceState, "ready">, { tone: "warning" | "danger"; text: string }> = {
  warming_up: {
    tone: "warning",
    text: "Policy Copilot is starting up. Answers will be available in a moment.",
  },
  unavailable: {
    tone: "danger",
    text: "The answer service is unavailable right now. You can still read conversations and documents.",
  },
  unreachable: {
    tone: "danger",
    text: "Can't reach Policy Copilot. Check your connection; this message clears when it's back.",
  },
};

/**
 * Shows a banner only when the service isn't ready. Pauses while the tab is
 * hidden and re-checks as soon as it's visible again or the network returns.
 */
export function ServiceBanner() {
  const [state, setState] = useState<ServiceState>("ready");
  const wake = useWakeState();

  useEffect(() => {
    let timer: number | undefined;
    let controller: AbortController | undefined;

    const check = async () => {
      window.clearTimeout(timer);
      if (document.hidden) return;
      controller?.abort();
      controller = new AbortController();
      try {
        const next = await getServiceState(controller.signal);
        setState(next);
        timer = window.setTimeout(check, next === "ready" ? RECHECK_READY_MS : RECHECK_DEGRADED_MS);
      } catch {
        // Aborted by a newer check.
      }
    };

    const onVisible = () => !document.hidden && void check();
    const onOffline = () => setState("unreachable");
    void check();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    window.addEventListener("offline", onOffline);
    return () => {
      window.clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  // While a sleeping API is waking, WakeNotice explains it; don't double up.
  if (state === "ready" || wake !== "awake") return null;
  const message = MESSAGES[state];

  return (
    <div className="shrink-0 border-b border-line px-3 py-2 md:px-4">
      <Notice tone={message.tone}>{message.text}</Notice>
    </div>
  );
}
