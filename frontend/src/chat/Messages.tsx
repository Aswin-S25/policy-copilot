import type { Citation, ConversationMessage } from "../api/types";
import { CitationContext } from "../sources/citations";
import { SourcesStrip } from "../sources/SourcesStrip";
import { Button } from "../ui/Button";
import { Notice, Spinner } from "../ui/feedback";
import { LockIcon, RetryIcon } from "../ui/icons";
import { useCountdown } from "./hooks";
import { Markdown } from "./Markdown";
import type { Turn } from "./turns";

/** Which answer's sources are open, and how to open another. */
export interface SourcesControl {
  activeKey: string | null;
  activeSource: number | null;
  open: (key: string, answer: string, citations: Citation[], source: number | null) => void;
}

/**
 * An answer with its evidence. `citations` is null while the answer is
 * still streaming: markers render, but inert, until the server's list arrives.
 */
function Answer({
  answerKey,
  text,
  citations,
  sources,
}: {
  answerKey: string;
  text: string;
  citations: Citation[] | null;
  sources: SourcesControl;
}) {
  const activeSource = sources.activeKey === answerKey ? sources.activeSource : null;
  const open = (source: number | null) => citations && sources.open(answerKey, text, citations, source);

  return (
    <div>
      <CitationContext.Provider value={{ citations, activeSource, open }}>
        <Markdown text={text} />
      </CitationContext.Provider>
      {citations && (
        <SourcesStrip answer={text} citations={citations} activeSource={activeSource} onOpen={open} />
      )}
    </div>
  );
}

export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-[14px] bg-sunken px-4 py-2.5 text-body whitespace-pre-wrap text-ink [overflow-wrap:anywhere]">
        {text}
      </div>
    </div>
  );
}

export function SavedMessage({ message, sources }: { message: ConversationMessage; sources: SourcesControl }) {
  if (message.sender === "user") return <UserMessage text={message.content} />;

  if (message.withheld) {
    return (
      <div className="flex items-start gap-2.5 rounded-control border border-dashed border-line-strong px-3.5 py-3 text-ui text-muted">
        <LockIcon size={16} className="mt-0.5 shrink-0" />
        <p>{message.content}.</p>
      </div>
    );
  }

  // `citations` is absent only if the API predates citations in history.
  return (
    <Answer answerKey={message.id} text={message.content} citations={message.citations ?? null} sources={sources} />
  );
}

function Progress({ label }: { label: string }) {
  return (
    <div role="status" className="flex items-center gap-2 text-ui text-muted">
      <Spinner size={14} />
      <span>{label}</span>
    </div>
  );
}

interface TurnViewProps {
  turn: Turn;
  onRetry: () => void;
  onEdit: () => void;
  sources: SourcesControl;
}

/** A question that isn't part of the saved conversation yet: in flight, saved-pending-reload, or failed. */
export function TurnView({ turn, onRetry, onEdit, sources }: TurnViewProps) {
  const rewritten = turn.standalone && turn.standalone.trim() !== turn.question.trim();

  return (
    <>
      <UserMessage text={turn.question} />
      <div aria-busy={turn.phase === "writing" || undefined} className="space-y-3">
        {rewritten && (
          <p className="text-meta text-faint">
            Searched for: <span className="text-muted">{turn.standalone}</span>
          </p>
        )}
        <TurnBody turn={turn} onRetry={onRetry} onEdit={onEdit} sources={sources} />
      </div>
    </>
  );
}

function TurnBody({ turn, onRetry, onEdit, sources }: TurnViewProps) {
  const wait = useCountdown(turn.retryAt);
  // Once saved, key by message id: the same key the reloaded message will
  // have, so an open sources panel stays attached through the reload.
  const answerKey = turn.messageId ?? `turn-${turn.id}`;

  switch (turn.phase) {
    case "sending":
    case "searching":
      return <Progress label="Searching the policies you can access…" />;

    case "writing":
      return turn.draft ? (
        <>
          <Answer answerKey={answerKey} text={turn.draft} citations={null} sources={sources} />
          <Progress label="Writing…" />
        </>
      ) : (
        <Progress label="Writing the answer…" />
      );

    case "saved":
      return (
        <Answer answerKey={answerKey} text={turn.answer ?? turn.draft} citations={turn.citations} sources={sources} />
      );

    case "checking":
      return <Progress label="Connection lost. Checking whether the answer was saved…" />;

    case "failed":
    case "stopped": {
      const actions = (
        <div className="flex gap-1.5">
          <Button size="sm" variant="ghost" onClick={onEdit}>
            Edit question
          </Button>
          <Button size="sm" icon={<RetryIcon size={14} />} onClick={onRetry} disabled={wait > 0}>
            {wait > 0 ? `Retry in ${wait} s` : "Retry"}
          </Button>
        </div>
      );
      return turn.phase === "stopped" ? (
        <Notice action={actions}>Stopped. This question wasn't saved.</Notice>
      ) : (
        <Notice tone="danger" action={actions}>
          {turn.error ?? "The answer couldn't be produced."} This question wasn't saved.
        </Notice>
      );
    }
  }
}
