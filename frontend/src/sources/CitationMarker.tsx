import { useContext, useId, useRef, useState } from "react";
import type { Citation } from "../api/types";
import { CitationContext, formatSection } from "./citations";

const TIP_WIDTH = 288;

/**
 * Inline "[Source N]" marker. With citation data it is a button that
 * previews the document and section on hover/focus and opens the source
 * panel on click; without data (still streaming, or a number the server
 * didn't provide) it is an inert label.
 */
export function CitationMarker({ number }: { number: number }) {
  const scope = useContext(CitationContext);
  const citation = scope?.citations?.find((item) => item.source === number);
  const button = useRef<HTMLButtonElement>(null);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const tipId = useId();

  if (!scope || !citation) {
    return (
      <span className="cite cite-inert" aria-label={`Source ${number}`}>
        {number}
      </span>
    );
  }

  const show = () => setAnchor(button.current?.getBoundingClientRect() ?? null);
  const hide = () => setAnchor(null);
  const active = scope.activeSource === number;

  return (
    <>
      <button
        ref={button}
        type="button"
        className="cite"
        data-active={active || undefined}
        aria-label={`Source ${number}: ${citation.document}`}
        aria-describedby={anchor ? tipId : undefined}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onKeyDown={(event) => event.key === "Escape" && hide()}
        onClick={() => {
          hide();
          scope.open(number);
        }}
      >
        {number}
      </button>
      {anchor && <SourceTip id={tipId} anchor={anchor} citation={citation} />}
    </>
  );
}

/** Fixed-position preview, clamped to the viewport so scroll containers can't clip it. */
function SourceTip({ id, anchor, citation }: { id: string; anchor: DOMRect; citation: Citation }) {
  const left = Math.min(
    Math.max(8, anchor.left + anchor.width / 2 - TIP_WIDTH / 2),
    window.innerWidth - TIP_WIDTH - 8,
  );
  const above = anchor.top > 120;
  const section = formatSection(citation.section, citation.document);

  return (
    <span
      id={id}
      role="tooltip"
      className="pointer-events-none fixed z-50 block rounded-control border border-line bg-surface px-3 py-2.5 shadow-overlay"
      style={{
        width: TIP_WIDTH,
        left,
        top: above ? anchor.top - 8 : anchor.bottom + 8,
        transform: above ? "translateY(-100%)" : undefined,
      }}
    >
      <span className="block font-serif text-[0.9375rem] leading-snug font-medium text-ink">
        {citation.document}
      </span>
      {section && <span className="mt-0.5 block text-meta text-muted">{section}</span>}
    </span>
  );
}
