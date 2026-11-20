import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { IconButton } from "../ui/Button";
import { ArrowUpIcon, StopIcon } from "../ui/icons";

/** Matches MessageRequest.question (min_length=1, max_length=2000) in the API. */
export const MAX_QUESTION_CHARS = 2000;
const COUNTER_FROM = MAX_QUESTION_CHARS - 200;
const MAX_HEIGHT_PX = 240;

interface ComposerProps {
  /** Omit to render the composer read-only (e.g. while a view is loading). */
  onSubmit?: (question: string) => void;
  /** A turn is in flight: sending is blocked and Stop is offered instead. */
  busy?: boolean;
  onStop?: () => void;
  /** Blocks sending with a visible reason (rate limit, service unavailable). */
  blockedReason?: string;
  autoFocus?: boolean;
  /** Text to restore, e.g. a question whose turn failed. Applied when it changes. */
  restore?: { text: string; key: number };
}

export function Composer({ onSubmit, busy, onStop, blockedReason, autoFocus, restore }: ComposerProps) {
  const [value, setValue] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);

  // Grow with the content up to a cap, then scroll inside.
  useEffect(() => {
    const el = textarea.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  useEffect(() => {
    if (restore) {
      setValue(restore.text);
      textarea.current?.focus();
    }
  }, [restore]);

  const trimmed = value.trim();
  const tooLong = value.length > MAX_QUESTION_CHARS;
  const canSend = Boolean(onSubmit) && !busy && !blockedReason && trimmed.length > 0 && !tooLong;

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!canSend || !onSubmit) return;
    onSubmit(trimmed);
    setValue("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends; Shift+Enter is a newline; never send mid-IME composition.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  const showCounter = value.length >= COUNTER_FROM;

  return (
    <form onSubmit={submit} className="mx-auto w-full max-w-[46rem]">
      <div
        className={
          "rounded-panel border bg-surface shadow-composer transition-colors duration-150 " +
          "focus-within:border-accent/60 " +
          (tooLong ? "border-danger/60" : "border-line-strong")
        }
      >
        <label htmlFor="composer-input" className="sr-only">
          Ask a question about company policy
        </label>
        <textarea
          id="composer-input"
          ref={textarea}
          rows={1}
          value={value}
          autoFocus={autoFocus}
          readOnly={!onSubmit}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about a policy…"
          aria-describedby="composer-hint"
          aria-invalid={tooLong || undefined}
          className={
            "scroll-quiet block w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-body " +
            "text-ink placeholder:text-faint focus:outline-none focus-visible:outline-none"
          }
        />
        <div className="flex items-center justify-between gap-3 px-2.5 pb-2.5 pl-4">
          <span id="composer-hint" className="min-w-0 truncate text-meta text-faint">
            {blockedReason ? (
              <span className="text-warning">{blockedReason}</span>
            ) : showCounter ? (
              <span className={`tabular ${tooLong ? "text-danger" : ""}`}>
                {value.length.toLocaleString()} / {MAX_QUESTION_CHARS.toLocaleString()} characters
              </span>
            ) : (
              <span className="hidden sm:inline">Enter to send, Shift + Enter for a new line</span>
            )}
          </span>

          {busy ? (
            <IconButton label="Stop generating" variant="primary" onClick={onStop} disabled={!onStop}>
              <StopIcon size={16} />
            </IconButton>
          ) : (
            <IconButton label="Send question" variant="primary" type="submit" disabled={!canSend}>
              <ArrowUpIcon size={16} />
            </IconButton>
          )}
        </div>
      </div>
    </form>
  );
}
