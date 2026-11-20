import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError } from "../api/client";
import { listConversations } from "../api/conversations";
import type { ConversationSummary } from "../api/types";
import { startTurn } from "../chat/turns";

type ListStatus = "loading" | "ready" | "error";

interface ConversationsValue {
  status: ListStatus;
  items: ConversationSummary[];
  error: string | null;
  /** Re-reads the list; keeps showing the current items meanwhile. */
  refresh: () => void;
  /** Adds or replaces one entry, newest first, before the server list catches up. */
  upsert: (summary: ConversationSummary) => void;
  remove: (id: string) => void;
  /** Sends a question and keeps the list in step with the server's titles. */
  ask: (conversationId: string, question: string, baseline: number) => void;
}

const ConversationsContext = createContext<ConversationsValue | null>(null);

export function useConversations(): ConversationsValue {
  const value = useContext(ConversationsContext);
  if (!value) throw new Error("useConversations must be used inside <ConversationsProvider>");
  return value;
}

export function ConversationsProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<ListStatus>("loading");
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    latest.current?.abort(); // only the newest response may win
    const controller = new AbortController();
    latest.current = controller;
    try {
      const { conversations } = await listConversations({ signal: controller.signal });
      if (controller.signal.aborted) return;
      setItems(conversations);
      setStatus("ready");
      setError(null);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof ApiError ? err.message : "Couldn't load your conversations.");
      setStatus((current) => (current === "ready" ? "ready" : "error"));
    }
  }, []);

  useEffect(() => {
    void load();
    return () => latest.current?.abort();
  }, [load]);

  const refresh = useCallback(() => void load(), [load]);

  const upsert = useCallback((summary: ConversationSummary) => {
    setItems((current) => [summary, ...current.filter((item) => item.id !== summary.id)]);
  }, []);

  const remove = useCallback((id: string) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const ask = useCallback(
    (conversationId: string, question: string, baseline: number) => {
      startTurn(conversationId, question, baseline, {
        onQuestionStored: refresh, // title is set and updated_at moved
        onSettled: refresh,
      });
    },
    [refresh],
  );

  const value = useMemo(
    () => ({ status, items, error, refresh, upsert, remove, ask }),
    [status, items, error, refresh, upsert, remove, ask],
  );

  return <ConversationsContext.Provider value={value}>{children}</ConversationsContext.Provider>;
}

export const UNTITLED = "New conversation";

export interface ConversationGroup {
  label: string;
  items: ConversationSummary[];
}

/** Groups by last activity: Today, Yesterday, Previous 7 days, Previous 30 days, Older. */
export function groupByRecency(items: ConversationSummary[], now = new Date()): ConversationGroup[] {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 24 * 60 * 60 * 1000;
  const buckets: [string, number][] = [
    ["Today", startOfToday],
    ["Yesterday", startOfToday - day],
    ["Previous 7 days", startOfToday - 7 * day],
    ["Previous 30 days", startOfToday - 30 * day],
    ["Older", -Infinity],
  ];

  const groups = new Map<string, ConversationSummary[]>();
  for (const item of items) {
    const updated = new Date(item.updated_at).getTime();
    const [label] = buckets.find(([, from]) => updated >= from)!;
    groups.set(label, [...(groups.get(label) ?? []), item]);
  }
  return buckets
    .filter(([label]) => groups.has(label))
    .map(([label]) => ({ label, items: groups.get(label)! }));
}
