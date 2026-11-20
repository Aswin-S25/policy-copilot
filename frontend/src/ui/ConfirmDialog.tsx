import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "./Button";
import { Notice, Spinner } from "./feedback";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  busyLabel: string;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Modal confirmation on the native <dialog>: the browser provides the focus
 * trap, Escape handling, inert background and focus return on close.
 */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  busyLabel,
  busy,
  error,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault(); // close through state, not by the browser alone
        if (!busy) onCancel();
      }}
      // Escape here must not also close panels listening on window.
      onKeyDown={(event) => event.key === "Escape" && event.stopPropagation()}
      className={
        "m-auto w-[min(420px,calc(100vw-32px))] rounded-panel border border-line bg-surface p-0 " +
        "text-ink shadow-overlay backdrop:bg-ink/30"
      }
    >
      <form
        className="p-5"
        onSubmit={(event) => {
          event.preventDefault();
          if (!busy) onConfirm();
        }}
      >
        <h2 id={titleId} className="text-lead font-semibold tracking-[-0.01em]">
          {title}
        </h2>
        <div className="mt-2 text-control text-muted">{children}</div>

        {error && (
          <div className="mt-4">
            <Notice tone="danger">{error}</Notice>
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <Button onClick={onCancel} disabled={busy} autoFocus>
            Cancel
          </Button>
          <Button type="submit" variant="danger" disabled={busy}>
            {busy ? (
              <>
                <Spinner size={14} /> {busyLabel}
              </>
            ) : (
              confirmLabel
            )}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
