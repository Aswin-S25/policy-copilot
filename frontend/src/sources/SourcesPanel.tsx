import { useEffect, useId, useRef, useState } from "react";
import { ApiError } from "../api/client";
import { cachedPassage, getPassage } from "../api/sources";
import type { Citation, SourcePassage } from "../api/types";
import { Markdown } from "../chat/Markdown";
import { useMediaQuery } from "../layout/shell";
import { IconButton } from "../ui/Button";
import { Spinner } from "../ui/feedback";
import { ChevronRightIcon, CloseIcon } from "../ui/icons";
import { formatSection, partitionCitations } from "./citations";

export interface SourcesSelection {
  /** Which answer the panel describes (message id, or turn id while live). */
  key: string;
  answer: string;
  citations: Citation[];
  active: number | null;
  /** Changes on every open, so re-selecting the same source replays the highlight. */
  nonce: number;
}

// Inline beside the conversation only when both still have room to read:
// at 1024px the sidebar + panel left the answer column ~300px wide.
const WIDE_QUERY = "(min-width: 1280px)";

interface PanelProps {
  selection: SourcesSelection;
  onSelect: (source: number) => void;
  onClose: () => void;
}

/**
 * Source details beside the conversation (overlay below 1024px). Cited
 * sources come first; sources the model was given but did not cite are
 * listed separately so evidence and context are never confused.
 */
export function SourcesPanel({ selection, onSelect, onClose }: PanelProps) {
  const wide = useMediaQuery(WIDE_QUERY);
  const heading = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  const { cited, reviewed } = partitionCitations(selection.answer, selection.citations);

  // Move focus into the panel when it opens or switches answer, and give it
  // back to whatever opened it when it closes.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    heading.current?.focus({ preventScroll: true });
    return () => {
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, [selection.key]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const body = (
    <aside
      aria-labelledby={headingId}
      className={
        "flex h-full flex-col bg-surface " +
        (wide ? "w-[400px] shrink-0 border-l border-line" : "w-full max-w-[440px] shadow-overlay")
      }
    >
      <div className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-line pr-2 pl-5">
        <h2 id={headingId} ref={heading} tabIndex={-1} className="text-control font-medium text-ink focus:outline-none">
          Sources
        </h2>
        <IconButton label="Close sources" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </div>

      <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-3 pt-4 pb-8">
        {cited.length > 0 && (
          <SourceGroup
            title="Cited in this answer"
            citations={cited}
            selection={selection}
            onSelect={onSelect}
          />
        )}
        {reviewed.length > 0 && (
          <SourceGroup
            title="Also reviewed"
            note="Given to the copilot for this question but not cited in the answer."
            citations={reviewed}
            selection={selection}
            onSelect={onSelect}
          />
        )}
      </div>
    </aside>
  );

  if (wide) return body;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div aria-hidden="true" onClick={onClose} className="absolute inset-0 bg-ink/25" />
      <div role="dialog" aria-modal="true" aria-labelledby={headingId} className="relative flex h-full w-full justify-end">
        {body}
      </div>
    </div>
  );
}

function SourceGroup({
  title,
  note,
  citations,
  selection,
  onSelect,
}: {
  title: string;
  note?: string;
  citations: Citation[];
  selection: SourcesSelection;
  onSelect: (source: number) => void;
}) {
  return (
    <section className="mb-6 last:mb-0">
      <h3 className="px-2 text-meta font-medium text-muted">{title}</h3>
      {note && <p className="mt-0.5 px-2 text-meta text-faint">{note}</p>}
      <ul className="mt-2 space-y-1">
        {citations.map((citation) => (
          <li key={citation.source}>
            <SourceItem
              citation={citation}
              active={selection.active === citation.source}
              nonce={selection.nonce}
              onSelect={() => onSelect(citation.source)}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

function SourceItem({
  citation,
  active,
  nonce,
  onSelect,
}: {
  citation: Citation;
  active: boolean;
  nonce: number;
  onSelect: () => void;
}) {
  const [expanded, setExpanded] = useState(active);
  const item = useRef<HTMLDivElement>(null);
  const passageId = useId();
  const section = formatSection(citation.section, citation.document);

  // Selecting a source (from a marker or chip) expands and reveals it.
  useEffect(() => {
    if (!active) return;
    setExpanded(true);
    item.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [active, nonce]);

  return (
    <div
      ref={item}
      className={
        "rounded-panel border transition-colors duration-150 " +
        (active ? "border-marker-edge bg-surface" : "border-transparent hover:bg-canvas")
      }
    >
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={passageId}
        onClick={() => {
          if (!expanded) onSelect();
          setExpanded(!expanded);
        }}
        className="flex w-full items-start gap-3 rounded-panel px-2 py-2.5 text-left"
      >
        <span className={`source-number ${active ? "source-number-active" : ""}`}>{citation.source}</span>
        <span className="min-w-0 flex-1">
          <span className="block font-serif text-[0.9375rem] leading-snug font-medium text-ink">
            {citation.document}
          </span>
          {section && <span className="mt-0.5 block text-meta text-muted">{section}</span>}
        </span>
        <ChevronRightIcon
          size={16}
          className={`mt-0.5 shrink-0 text-faint transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}
        />
      </button>

      {expanded && (
        <div id={passageId} className="px-2 pb-3 pl-11">
          <Passage chunkId={citation.chunk_id} highlight={active} nonce={nonce} />
        </div>
      )}
    </div>
  );
}

type PassageState =
  | { status: "loading" }
  | { status: "ready"; passage: SourcePassage }
  | { status: "error"; message: string };

function Passage({ chunkId, highlight, nonce }: { chunkId: string; highlight: boolean; nonce: number }) {
  const [state, setState] = useState<PassageState>(() => {
    const hit = cachedPassage(chunkId);
    return hit ? { status: "ready", passage: hit } : { status: "loading" };
  });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getPassage(chunkId)
      .then((passage) => !cancelled && setState({ status: "ready", passage }))
      .catch((error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof ApiError && error.status === 404
            ? "This passage is no longer available. The document may have been updated, or your access has changed."
            : error instanceof ApiError
              ? error.message
              : "Couldn't load this passage.";
        setState({ status: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [chunkId, attempt]);

  if (state.status === "loading") {
    return (
      <div className="flex items-center gap-2 py-1 text-ui text-muted" role="status">
        <Spinner size={14} /> Loading the policy text…
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <p className="text-ui text-muted">
        {state.message}{" "}
        <button
          type="button"
          onClick={() => {
            setState({ status: "loading" });
            setAttempt((n) => n + 1);
          }}
          className="font-medium text-accent underline-offset-2 hover:underline"
        >
          Try again
        </button>
      </p>
    );
  }

  return (
    <figure>
      {/* key: replays the highlighter stroke each time this source is selected */}
      <blockquote key={highlight ? nonce : "plain"} className={`passage ${highlight ? "passage-active" : ""}`}>
        <Markdown text={state.passage.content} variant="policy" />
      </blockquote>
      <figcaption className="mt-1.5 text-meta text-faint">Quoted policy text</figcaption>
    </figure>
  );
}
