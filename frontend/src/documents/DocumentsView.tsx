import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { ApiError } from "../api/client";
import { listDocuments } from "../api/documents";
import type { DocumentSummary } from "../api/types";
import { useSession } from "../auth/AuthContext";
import { documentRoles, roleName } from "../auth/session";
import { ViewHeader } from "../layout/ViewHeader";
import { Button } from "../ui/Button";
import { Notice } from "../ui/feedback";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; documents: DocumentSummary[] }
  | { status: "error"; message: string };

const STATUS: Record<DocumentSummary["status"], { label: string; dot: string; hint: string }> = {
  ready: { label: "Ready", dot: "bg-accent", hint: "Searchable in answers." },
  indexing: {
    label: "Indexing",
    dot: "bg-marker-edge",
    hint: "Still being processed. Parts of it may not appear in answers yet.",
  },
  empty: { label: "No text", dot: "bg-line-strong", hint: "No searchable text was found in this document." },
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/**
 * The policy documents the signed-in user can search. The list comes from
 * the server already filtered by the user's roles; nothing is hidden here.
 */
export function DocumentsView() {
  const session = useSession();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [query, setQuery] = useState("");
  const searchId = useId();

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const { documents } = await listDocuments(signal);
      if (!signal?.aborted) setState({ status: "ready", documents });
    } catch (error) {
      if (signal?.aborted) return;
      setState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Couldn't load the document list.",
      });
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const documents = state.status === "ready" ? state.documents : [];
  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return needle ? documents.filter((doc) => doc.title.toLocaleLowerCase().includes(needle)) : documents;
  }, [documents, query]);

  const roles = documentRoles(session).map(roleName);

  return (
    <>
      <ViewHeader title="Policy documents" />

      <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[60rem] px-5 pt-8 pb-12 md:px-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="max-w-[36rem]">
              <h2 className="text-heading font-semibold tracking-[-0.015em] text-ink">Policy documents</h2>
              <p className="mt-1.5 text-control text-muted">
                {roles.length > 0
                  ? `The documents Policy Copilot can use to answer you, based on your ${roles.join(", ")} access.`
                  : "Your account has no document access, so no documents are available."}
              </p>
            </div>
            {state.status === "ready" && documents.length > 0 && (
              <div className="w-full sm:w-64">
                <label htmlFor={searchId} className="sr-only">
                  Filter documents by title
                </label>
                <input
                  id={searchId}
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Filter by title"
                  className={
                    "h-9 w-full rounded-control border border-line-strong bg-surface px-3 text-control text-ink " +
                    "placeholder:text-faint focus:border-accent focus:outline-none"
                  }
                />
              </div>
            )}
          </div>

          <div className="mt-6">
            {state.status === "loading" && <TableSkeleton />}

            {state.status === "error" && (
              <Notice
                tone="danger"
                action={
                  <Button size="sm" onClick={() => { setState({ status: "loading" }); void load(); }}>
                    Try again
                  </Button>
                }
              >
                {state.message}
              </Notice>
            )}

            {state.status === "ready" && documents.length === 0 && roles.length > 0 && (
              <p className="rounded-panel border border-dashed border-line-strong px-5 py-8 text-center text-control text-muted">
                No documents are shared with your roles yet.
              </p>
            )}

            {state.status === "ready" && documents.length > 0 && (
              <>
                <p className="mb-2 text-meta text-muted" aria-live="polite">
                  {visible.length === documents.length
                    ? `${documents.length} ${documents.length === 1 ? "document" : "documents"}`
                    : `${visible.length} of ${documents.length} documents`}
                </p>
                {visible.length === 0 ? (
                  <p className="rounded-panel border border-dashed border-line-strong px-5 py-8 text-center text-control text-muted">
                    No documents match “{query.trim()}”.
                  </p>
                ) : (
                  <DocumentTable documents={visible} />
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function DocumentTable({ documents }: { documents: DocumentSummary[] }) {
  return (
    <div className="overflow-hidden rounded-panel border border-line">
      <table className="w-full border-collapse text-left">
        <thead className="hidden bg-canvas md:table-header-group">
          <tr className="text-meta text-muted">
            <th scope="col" className="px-4 py-2.5 font-medium">Document</th>
            <th scope="col" className="px-4 py-2.5 font-medium">Your access</th>
            <th scope="col" className="px-4 py-2.5 font-medium">Status</th>
            <th scope="col" className="px-4 py-2.5 text-right font-medium">Updated</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => {
            const status = STATUS[doc.status];
            return (
              <tr
                key={doc.id}
                className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 border-t border-line px-4 py-3 first:border-t-0 md:table-row md:px-0 md:py-0"
              >
                <td className="col-span-2 md:px-4 md:py-3">
                  <span className="block font-serif text-[0.9375rem] leading-snug font-medium text-ink">
                    {doc.title}
                  </span>
                  <span className="mt-0.5 block text-meta text-muted">
                    {doc.section_count} {doc.section_count === 1 ? "section" : "sections"}
                    {doc.document_type === "markdown" ? ", Markdown" : `, ${doc.document_type}`}
                  </span>
                </td>
                <td className="md:px-4 md:py-3">
                  <span className="sr-only md:hidden">Your access: </span>
                  <span className="flex flex-wrap gap-1">
                    {doc.access.map((role) => (
                      <span
                        key={role}
                        className="inline-flex h-5 items-center rounded-[4px] bg-sunken px-1.5 text-meta text-ink-soft"
                      >
                        {roleName(role)}
                      </span>
                    ))}
                  </span>
                </td>
                <td className="text-right md:px-4 md:py-3 md:text-left">
                  <span className="inline-flex items-center gap-1.5 text-ui text-ink-soft" title={status.hint}>
                    <span aria-hidden="true" className={`size-1.5 rounded-full ${status.dot}`} />
                    {status.label}
                    <span className="sr-only">. {status.hint}</span>
                  </span>
                </td>
                <td className="col-span-2 text-meta text-muted md:px-4 md:py-3 md:text-right md:text-ui">
                  <span className="md:hidden">Updated </span>
                  <time dateTime={doc.updated_at} className="tabular">{formatDate(doc.updated_at)}</time>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading documents" className="overflow-hidden rounded-panel border border-line">
      {[70, 55, 80, 62].map((width) => (
        <div key={width} className="flex items-center gap-4 border-t border-line px-4 py-4 first:border-t-0">
          <div className="h-3 animate-pulse rounded-full bg-sunken" style={{ width: `${width / 2}%` }} />
          <div className="ml-auto h-3 w-16 animate-pulse rounded-full bg-sunken" />
        </div>
      ))}
    </div>
  );
}
