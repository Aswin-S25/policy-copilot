import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { getConversation } from "../api/conversations";
import type { Citation, ConversationDetail } from "../api/types";
import { SourcesPanel, type SourcesSelection } from "../sources/SourcesPanel";
import { UNTITLED, useConversations } from "../conversations/ConversationsContext";
import { ViewHeader } from "../layout/ViewHeader";
import { useShell } from "../layout/shell";
import { DeleteConversationDialog } from "../conversations/DeleteConversationDialog";
import { Button, IconButton } from "../ui/Button";
import { TrashIcon } from "../ui/icons";
import { Notice } from "../ui/feedback";
import { Composer } from "./Composer";
import { useCountdown, useStickToBottom } from "./hooks";
import { SavedMessage, TurnView, type SourcesControl } from "./Messages";
import { clearTurn, isInFlight, resolveCheck, stopTurn, useTurn } from "./turns";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; detail: ConversationDetail }
  | { status: "error"; error: ApiError };

export function ConversationView() {
  const { conversationId = "" } = useParams();
  // Remount per conversation: no state leaks from one to the next.
  return <Conversation key={conversationId} id={conversationId} />;
}

function Conversation({ id }: { id: string }) {
  const { ask, refresh } = useConversations();
  const { isDesktop } = useShell();
  const turn = useTurn(id);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [restore, setRestore] = useState<{ text: string; key: number }>();
  const [selection, setSelection] = useState<SourcesSelection | null>(null);
  const [deleting, setDeleting] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  const sources = useMemo<SourcesControl>(
    () => ({
      activeKey: selection?.key ?? null,
      activeSource: selection?.active ?? null,
      open: (key: string, answer: string, citations: Citation[], source: number | null) =>
        setSelection({ key, answer, citations, active: source, nonce: Date.now() }),
    }),
    [selection?.key, selection?.active],
  );
  const closeSources = useCallback(() => setSelection(null), []);
  const selectSource = useCallback(
    (source: number) => setSelection((current) => current && { ...current, active: source, nonce: Date.now() }),
    [],
  );

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const detail = await getConversation(id, signal);
        if (!signal?.aborted) setState({ status: "ready", detail });
        return detail;
      } catch (error) {
        if (signal?.aborted) return undefined;
        const apiError = error instanceof ApiError ? error : new ApiError(500, "Couldn't open this conversation.");
        setState((current) => (current.status === "ready" ? current : { status: "error", error: apiError }));
        return undefined;
      }
    },
    [id],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  // Once a turn has ended, reload the server's copy, then drop the local turn.
  // The reload and the removal are applied together so the answer never
  // disappears or shows twice.
  useEffect(() => {
    if (!turn || (turn.phase !== "saved" && turn.phase !== "checking")) return;
    let cancelled = false;

    void getConversation(id)
      .then((detail) => {
        if (cancelled) return;
        const stored = detail.messages.length >= turn.baseline + 2;
        flushSync(() => setState({ status: "ready", detail }));
        if (turn.phase === "checking") resolveCheck(id, turn.id, stored);
        else if (stored) clearTurn(id, turn.id);
      })
      .catch(() => {
        if (!cancelled && turn.phase === "checking") resolveCheck(id, turn.id, false);
      });

    return () => {
      cancelled = true;
    };
  }, [id, turn]);

  const detail = state.status === "ready" ? state.detail : undefined;
  // While a turn is shown, the server copy is cut at the turn's baseline:
  // its question may already be stored, and must not appear twice.
  const messages = detail ? (turn ? detail.messages.slice(0, turn.baseline) : detail.messages) : [];
  const repin = useStickToBottom(scroller, `${messages.length}:${turn?.phase}:${turn?.draft.length}`);

  const busy = isInFlight(turn);
  const waitSeconds = useCountdown(turn?.retryAt);
  const blockedReason =
    waitSeconds > 0 ? `Question limit reached. You can ask again in ${waitSeconds} s.` : undefined;

  function send(question: string) {
    if (!detail) return;
    clearTurn(id); // replaces a failed or stopped turn, if any
    ask(id, question, detail.messages.length);
    repin();
  }

  function retry() {
    if (!turn) return;
    const question = turn.question;
    clearTurn(id, turn.id);
    ask(id, question, turn.baseline);
    repin();
  }

  function edit() {
    if (!turn) return;
    setRestore({ text: turn.question, key: Date.now() });
    clearTurn(id, turn.id);
  }

  const title = detail?.title ?? turn?.question ?? (state.status === "loading" ? "" : UNTITLED);

  if (state.status === "error" && !turn) {
    return (
      <>
        <ViewHeader title="Conversation" />
        <LoadError error={state.error} onRetry={() => { setState({ status: "loading" }); void load(); refresh(); }} />
      </>
    );
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <ViewHeader
          title={title}
          actions={
            detail && (
              <IconButton label="Delete conversation" onClick={() => setDeleting(true)}>
                <TrashIcon size={17} />
              </IconButton>
            )
          }
        />

        <div ref={scroller} className="scroll-quiet min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[46rem] px-5 pt-8 pb-10 md:px-6">
            {state.status === "loading" && !turn ? (
              <MessagesSkeleton />
            ) : (
              <div className="space-y-7">
                {messages.map((message) => (
                  <SavedMessage key={message.id} message={message} sources={sources} />
                ))}
                {turn && <TurnView turn={turn} onRetry={retry} onEdit={edit} sources={sources} />}
              </div>
            )}
          </div>
        </div>

        <div className="shrink-0 px-3 pt-2 pb-3 md:px-6 md:pb-5">
          <Composer
            onSubmit={detail ? send : undefined}
            busy={busy}
            onStop={() => stopTurn(id)}
            blockedReason={blockedReason}
            autoFocus={isDesktop}
            restore={restore}
          />
        </div>
      </div>

      {selection && <SourcesPanel selection={selection} onSelect={selectSource} onClose={closeSources} />}

      <DeleteConversationDialog
        conversation={deleting && detail ? { id, title: detail.title } : null}
        onClose={() => setDeleting(false)}
      />
    </div>
  );
}

function MessagesSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading conversation" className="space-y-7">
      <div className="flex justify-end">
        <div className="h-10 w-2/5 animate-pulse rounded-[14px] bg-sunken" />
      </div>
      <div className="space-y-2.5">
        {[96, 88, 92, 60].map((width) => (
          <div key={width} className="h-3 animate-pulse rounded-full bg-sunken" style={{ width: `${width}%` }} />
        ))}
      </div>
    </div>
  );
}

function LoadError({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  if (error.status === 404) {
    return (
      <div className="mx-auto flex w-full max-w-[46rem] flex-1 flex-col justify-center px-6">
        <h2 className="text-heading font-semibold text-ink">This conversation isn't available</h2>
        <p className="mt-2 text-body text-muted">
          It may have been deleted, or it belongs to another account.{" "}
          <Link to="/" className="font-medium text-accent underline-offset-2 hover:underline">
            Start a new conversation
          </Link>
          .
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-[46rem] flex-1 flex-col justify-center px-6">
      <Notice tone="danger" action={<Button size="sm" onClick={onRetry}>Try again</Button>}>
        {error.message}
      </Notice>
    </div>
  );
}
