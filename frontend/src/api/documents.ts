import { requestJson } from "./client";
import type { DocumentSummary } from "./types";

export function listDocuments(signal?: AbortSignal) {
  return requestJson<{ documents: DocumentSummary[] }>("/documents", { signal });
}
