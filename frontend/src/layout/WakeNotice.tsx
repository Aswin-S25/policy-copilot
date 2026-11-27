import { ensureAwake, useWakeState } from "../api/wake";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/feedback";
import { AlertIcon } from "../ui/icons";

/**
 * Shown on every screen while a sleeping API starts up (free hosting sleeps
 * when idle). The request that triggered it continues on its own.
 */
export function WakeNotice() {
  const state = useWakeState();
  if (state === "awake") return null;

  const waking = state === "waking";
  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-50 flex justify-center px-3">
      <div
        role={waking ? "status" : "alert"}
        className={
          "pointer-events-auto flex max-w-[34rem] items-center gap-3 rounded-panel border px-4 py-3 shadow-overlay " +
          (waking ? "border-line bg-surface text-ink" : "border-danger/30 bg-danger-soft text-danger")
        }
      >
        {waking ? <Spinner size={16} /> : <AlertIcon size={16} className="shrink-0" />}
        <div className="min-w-0 text-ui">
          {waking ? (
            <>
              <p className="font-medium">Waking up Policy Copilot. This may take up to a minute.</p>
              <p className="mt-0.5 text-muted">Your request will continue automatically.</p>
            </>
          ) : (
            <p>Policy Copilot didn't wake up. Check your connection, then try again.</p>
          )}
        </div>
        {!waking && (
          <Button size="sm" onClick={() => void ensureAwake().catch(() => {})}>
            Try again
          </Button>
        )}
      </div>
    </div>
  );
}
