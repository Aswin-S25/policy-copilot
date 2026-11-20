import type { Citation } from "../api/types";
import { partitionCitations } from "./citations";

interface SourcesStripProps {
  answer: string;
  citations: Citation[];
  activeSource: number | null;
  /** null opens the panel without selecting a source. */
  onOpen: (source: number | null) => void;
}

/**
 * The evidence line under an answer: the documents it cites, in the serif
 * document voice, set off from the generated text above by a rule.
 */
export function SourcesStrip({ answer, citations, activeSource, onOpen }: SourcesStripProps) {
  if (citations.length === 0) return null;
  const { cited, reviewed } = partitionCitations(answer, citations);

  return (
    <div className="mt-4 flex flex-wrap items-center gap-1.5 border-t border-line pt-3">
      {cited.map((citation) => (
        <button
          key={citation.source}
          type="button"
          onClick={() => onOpen(citation.source)}
          data-active={activeSource === citation.source || undefined}
          className="source-chip"
          title={citation.section ? `${citation.document}, ${citation.section}` : citation.document}
        >
          <span className="source-chip-number">{citation.source}</span>
          <span className="truncate font-serif">{citation.document}</span>
        </button>
      ))}
      {reviewed.length > 0 && (
        <button
          type="button"
          onClick={() => onOpen(null)}
          className="h-7 rounded-control px-2 text-ui text-muted transition-colors hover:bg-sunken hover:text-ink"
        >
          {cited.length > 0
            ? `${reviewed.length} more reviewed`
            : `Reviewed ${reviewed.length} ${reviewed.length === 1 ? "source" : "sources"}`}
        </button>
      )}
    </div>
  );
}
