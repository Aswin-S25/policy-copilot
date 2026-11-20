import { createContext } from "react";
import type { Citation } from "../api/types";

/**
 * The backend's citation syntax (app/rag/citations.py SOURCE_PATTERN).
 * Only this exact form is validated server-side, so only this form becomes
 * a clickable citation here.
 */
const SOURCE_MARKER = /\[Source\s+(\d+)\]/g;
const HAS_MARKER = /\[Source\s+\d+\]/;

export const CITATION_HREF = /^#source-(\d+)$/;

/** Source numbers that the answer text actually cites. */
export function citedNumbers(text: string): Set<number> {
  return new Set([...text.matchAll(SOURCE_MARKER)].map((match) => Number(match[1])));
}

/** Splits an answer's sources into the ones it cites and the ones only reviewed. */
export function partitionCitations(text: string, citations: Citation[]) {
  const cited = citedNumbers(text);
  return {
    cited: citations.filter((c) => cited.has(c.source)),
    reviewed: citations.filter((c) => !cited.has(c.source)),
  };
}

/**
 * "Leave Policy > Annual leave > Carry-over" -> "Annual leave › Carry-over".
 * A leading segment that repeats the document title shown right above it
 * is dropped; a path that is only the title becomes null.
 */
export function formatSection(path: string | null, documentTitle?: string): string | null {
  if (!path) return null;
  const parts = path.split(" > ").map((part) => part.trim()).filter(Boolean);
  const same = (a: string, b: string) => a.localeCompare(b, undefined, { sensitivity: "accent" }) === 0;
  // A path that is only the title (a document's introduction) adds nothing.
  if (documentTitle && parts.length > 0 && same(parts[0]!, documentTitle.trim())) parts.shift();
  return parts.length ? parts.join(" › ") : null;
}

// Minimal mdast shape; avoids depending on @types/mdast directly.
interface MdNode {
  type: string;
  value?: string;
  url?: string;
  children?: MdNode[];
}

/**
 * Remark plugin: "[Source 2]" in text becomes a link to "#source-2", which
 * the Markdown renderer draws as a citation marker. Works on the parsed
 * tree, so markers inside code and existing links are left untouched.
 */
export function remarkCitations() {
  return (tree: MdNode) => transform(tree);
}

function transform(node: MdNode) {
  if (!node.children || node.type === "link" || node.type === "linkReference") return;

  const next: MdNode[] = [];
  for (const child of node.children) {
    if (child.type !== "text" || !child.value || !HAS_MARKER.test(child.value)) {
      transform(child);
      next.push(child);
      continue;
    }

    let last = 0;
    for (const match of child.value.matchAll(SOURCE_MARKER)) {
      const index = match.index ?? 0;
      if (index > last) next.push({ type: "text", value: child.value.slice(last, index) });
      next.push({
        type: "link",
        url: `#source-${match[1]}`,
        children: [{ type: "text", value: match[1]! }],
      });
      last = index + match[0].length;
    }
    if (last < child.value.length) next.push({ type: "text", value: child.value.slice(last) });
  }
  node.children = next;
}

/**
 * Citations available to markers rendered inside one answer. `citations` is
 * null while the answer is still streaming: markers then render inert.
 */
export interface CitationScope {
  citations: Citation[] | null;
  activeSource: number | null;
  open: (source: number) => void;
}

export const CitationContext = createContext<CitationScope | null>(null);
