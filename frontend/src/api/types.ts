/*
  Response shapes, mirrored from the FastAPI code. Keep in sync with:
    app/api/conversations.py   conversation_summary(), read(), post_message_stream()
    app/conversations/service.py visible_messages()
    app/rag/pipeline.py         Citation.to_dict(), stream_answer_events()
*/

export interface ConversationSummary {
  id: string;
  /** Null until the first question is asked; then the question, truncated to 200 chars. */
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  position: number;
  sender: "user" | "assistant";
  content: string;
  /** True when the answer's source documents are no longer readable by this user. */
  withheld: boolean;
  /** Assistant answers: every source given to the model, numbered as in the text. Empty when withheld. */
  citations?: Citation[];
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[];
}

export interface Citation {
  /** The N in "[Source N]" markers inside the answer text. */
  source: number;
  document: string;
  /** "Heading > Subheading" path inside the document. */
  section: string | null;
  chunk_id: string;
  /** Retrieval score; present on live answers, null for answers loaded from history. */
  score: number | null;
}

/** GET /documents (app/api/documents.py): documents the caller's roles can read. */
export interface DocumentSummary {
  id: string;
  title: string;
  document_type: string;
  section_count: number;
  /** ready: searchable. indexing: still being embedded. empty: no searchable text. */
  status: "ready" | "indexing" | "empty";
  /** The caller's own roles that grant access (never the full access list). */
  access: string[];
  created_at: string;
  updated_at: string;
}

/** GET /chunks/{chunk_id} (app/api/sources.py). */
export interface SourcePassage {
  chunk_id: string;
  document_id: string;
  document_title: string;
  section_path: string | null;
  chunk_index: number;
  content: string;
}

/** Server-sent events of POST /conversations/{id}/messages/stream, in order. */
export type StreamEvent =
  | { event: "status"; data: { stage: string } }
  | { event: "question"; data: { standalone: string } }
  | { event: "token"; data: { text: string } }
  | { event: "answer"; data: { text: string } }
  | { event: "citations"; data: { sources: Citation[] } }
  | { event: "saved"; data: { message_id: string } }
  | { event: "error"; data: { detail: string } }
  | { event: "done"; data: Record<string, never> };
