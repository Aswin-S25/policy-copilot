import type { ReactNode } from "react";
import { AlertIcon } from "./icons";

export function Spinner({ size = 16, label }: { size?: number; label?: string }) {
  return (
    <span role={label ? "status" : undefined} className="inline-flex items-center">
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        className="animate-spin text-muted"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2.5" />
        <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
      {label && <span className="sr-only">{label}</span>}
    </span>
  );
}

/** Brand mark: the section sign, the most characteristic glyph of a policy. */
export function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <span
      aria-hidden="true"
      className="inline-flex shrink-0 items-center justify-center rounded-[6px] bg-accent font-serif text-white"
      style={{ width: size, height: size, fontSize: size * 0.68, lineHeight: 1 }}
    >
      <span style={{ transform: "translateY(-0.04em)" }}>§</span>
    </span>
  );
}

type Tone = "danger" | "warning" | "neutral";

const tones: Record<Tone, string> = {
  danger: "bg-danger-soft text-danger border-danger/20",
  warning: "bg-warning-soft text-warning border-warning/20",
  neutral: "bg-sunken text-ink-soft border-line",
};

/** Inline notice for errors and degraded states. Says what happened and what to do. */
export function Notice({
  tone = "neutral",
  children,
  action,
}: {
  tone?: Tone;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={`flex items-start gap-2.5 rounded-control border px-3 py-2.5 text-ui ${tones[tone]}`}
    >
      <AlertIcon size={16} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">{children}</div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
