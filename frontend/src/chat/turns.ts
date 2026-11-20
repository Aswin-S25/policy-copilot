/**
 * In-flight question turns, one per conversation, kept outside React views.
 *
 * A turn lives here from "send" until the conversation reloaded from the
 * server contains it. Keeping it outside the view means a stream keeps
 * going while the user opens another conversation, and comes back intact.
 *
 * Server contract (app/api/conversations.py post_message_stream):
 * - "answer" is authoritative and replaces the streamed tokens.
 * - A turn is stored only if "saved" arrives. On any failure, including a
 *   client disconnect, the server deletes the question, so history never
 *   holds a question without an answer. A failed turn is therefore shown
 *   as "not saved" with Retry, never as part of the conversation.
 */
import { useSyncExternalStore } from "react";
import { ApiError, isAbortError } from "../api/client";
import { streamMessage } from "../api/conversations";
import type { Citation } from "../api/types";

export type TurnPhase =
  | "sending" //     request sent, no event yet
  | "searching" //   follow-up rewrite + retrieval ("rewriting" stage)
  | "writing" //     model is generating
  | "saved" //       server stored the answer; waiting for the reload
  | "checking" //    stream broke off; asking the server whether it was saved
  | "failed" //      not saved; error explains why
  | "stopped"; //    the user stopped it; not saved

export interface Turn {
  id: number;
  conversationId: string;
  question: string;
  /** Messages that were in the conversation when this turn started. */
  baseline: number;
  phase: TurnPhase;
  /** The self-contained question the server searched with (follow-ups are rewritten). */
  standalone?: string;
  /** Raw tokens so far; provisional. */
  draft: string;
  /** Validated answer from the "answer" event; replaces the draft. */
  answer?: string;
  citations: Citation[];
  messageId?: string;
  error?: string;
  /** Epoch ms after which a rate-limited user may ask again. */
  retryAt?: number;
}

export interface TurnHooks {
  /** The question is stored and the conversation has its title. */
  onQuestionStored?: () => void;
  /** The stream ended, whatever the outcome. */
  onSettled?: () => void;
}

export const INTERRUPTED_MESSAGE = "The connection dropped before the answer was saved.";

const turns = new Map<string, Turn>();
const controllers = new Map<string, AbortController>();
const listeners = new Set<() => void>();
let nextId = 1;

function emit() {
  for (const listener of listeners) listener();
}

function update(conversationId: string, turnId: number, patch: Partial<Turn> | ((turn: Turn) => Partial<Turn>)) {
  const turn = turns.get(conversationId);
  if (!turn || turn.id !== turnId) return; // superseded or cleared
  const changes = typeof patch === "function" ? patch(turn) : patch;
  turns.set(conversationId, { ...turn, ...changes });
  emit();
}

export function isInFlight(turn: Turn | undefined): boolean {
  return turn?.phase === "sending" || turn?.phase === "searching" || turn?.phase === "writing";
}

/** Starts a turn. Ignored while another turn in this conversation is in flight. */
export function startTurn(conversationId: string, question: string, baseline: number, hooks: TurnHooks = {}) {
  if (isInFlight(turns.get(conversationId))) return;

  const id = nextId++;
  const controller = new AbortController();
  controllers.set(conversationId, controller);
  turns.set(conversationId, {
    id, conversationId, question, baseline, phase: "sending", draft: "", citations: [],
  });
  emit();

  void run(conversationId, id, question, controller, hooks);
}

async function run(
  conversationId: string,
  id: number,
  question: string,
  controller: AbortController,
  hooks: TurnHooks,
) {
  let serverError: string | undefined;
  const set = (patch: Partial<Turn> | ((turn: Turn) => Partial<Turn>)) => update(conversationId, id, patch);
  const saved = () => turns.get(conversationId)?.id === id && Boolean(turns.get(conversationId)?.messageId);

  try {
    for await (const event of streamMessage(conversationId, question, controller.signal)) {
      switch (event.event) {
        case "status":
          set({ phase: event.data.stage === "generation" ? "writing" : "searching" });
          break;
        case "question":
          set({ standalone: event.data.standalone });
          hooks.onQuestionStored?.();
          break;
        case "token":
          set((turn) => ({ phase: "writing", draft: turn.draft + event.data.text }));
          break;
        case "answer":
          set({ answer: event.data.text });
          break;
        case "citations":
          set({ citations: event.data.sources });
          break;
        case "saved":
          set({ messageId: event.data.message_id });
          break;
        case "error":
          serverError = event.data.detail;
          break;
        case "done":
          // The outcome is decided by "saved" / "error", checked below.
          break;
      }
    }

    if (saved()) set({ phase: "saved" });
    else if (serverError) set({ phase: "failed", error: serverError });
    else set({ phase: "checking" }); // ended without "saved" or "error": interrupted
  } catch (error) {
    if (saved()) {
      set({ phase: "saved" });
    } else if (isAbortError(error)) {
      set({ phase: "stopped" });
    } else if (error instanceof ApiError) {
      // Rejected before the stream opened: nothing was stored.
      set({
        phase: "failed",
        error: error.message,
        retryAt: error.status === 429 && error.retryAfter ? Date.now() + error.retryAfter * 1000 : undefined,
      });
    } else {
      // The stream broke mid-way. The server may have saved just before.
      set({ phase: "checking" });
    }
  } finally {
    if (controllers.get(conversationId) === controller) controllers.delete(conversationId);
    hooks.onSettled?.();
  }
}

export function stopTurn(conversationId: string) {
  controllers.get(conversationId)?.abort();
}

/** Resolves a "checking" turn once the server's copy of the conversation is known. */
export function resolveCheck(conversationId: string, turnId: number, wasSaved: boolean) {
  if (wasSaved) clearTurn(conversationId, turnId);
  else update(conversationId, turnId, { phase: "failed", error: INTERRUPTED_MESSAGE });
}

export function clearTurn(conversationId: string, turnId?: number) {
  const turn = turns.get(conversationId);
  if (!turn || (turnId !== undefined && turn.id !== turnId)) return;
  turns.delete(conversationId);
  emit();
}

/** Sign-out: stop every stream and forget all turns. */
export function abortAllTurns() {
  for (const controller of controllers.values()) controller.abort();
  controllers.clear();
  turns.clear();
  emit();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Current turn of a conversation, outside React (tests, event handlers). */
export function getTurn(conversationId: string): Turn | undefined {
  return turns.get(conversationId);
}

export function useTurn(conversationId: string | undefined): Turn | undefined {
  return useSyncExternalStore(subscribe, () => (conversationId ? turns.get(conversationId) : undefined));
}
