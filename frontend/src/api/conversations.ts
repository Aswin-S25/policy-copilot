import { request, requestJson } from "./client";
import { readEventStream } from "./sse";
import type { ConversationDetail, ConversationSummary, StreamEvent } from "./types";

export function listConversations(options: { signal?: AbortSignal; token?: string } = {}) {
  return requestJson<{ conversations: ConversationSummary[] }>("/conversations", options);
}

export function getConversation(id: string, signal?: AbortSignal) {
  return requestJson<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`, { signal });
}

export function createConversation() {
  // No title: the backend titles the conversation from its first question.
  return requestJson<ConversationSummary>("/conversations", { method: "POST" });
}

export function deleteConversation(id: string) {
  return requestJson<void>(`/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
}

const KNOWN_EVENTS = new Set([
  "status", "question", "token", "answer", "citations", "saved", "error", "done",
]);

/**
 * Asks a question in a conversation and yields the server's events.
 * HTTP errors before the stream opens (401, 404, 422, 429) throw ApiError.
 */
export async function* streamMessage(
  conversationId: string,
  question: string,
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await request(
    `/conversations/${encodeURIComponent(conversationId)}/messages/stream`,
    { method: "POST", body: { question }, signal, accept: "text/event-stream" },
  );

  for await (const raw of readEventStream(response)) {
    if (KNOWN_EVENTS.has(raw.event)) yield raw as StreamEvent;
  }
}
