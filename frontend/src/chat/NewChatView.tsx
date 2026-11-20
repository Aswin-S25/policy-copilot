import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { createConversation } from "../api/conversations";
import { useSession } from "../auth/AuthContext";
import { documentRoles, roleName } from "../auth/session";
import { useConversations } from "../conversations/ConversationsContext";
import { useShell } from "../layout/shell";
import { ViewHeader } from "../layout/ViewHeader";
import { Notice } from "../ui/feedback";
import { Composer } from "./Composer";

/**
 * A fresh conversation. Nothing is created on the server until the first
 * question is sent, so opening New chat never leaves empty history entries.
 */
export function NewChatView() {
  const { isDesktop } = useShell();
  const session = useSession();
  const { upsert, ask } = useConversations();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restore, setRestore] = useState<{ text: string; key: number }>();

  const roles = documentRoles(session);
  const noAccess = roles.length === 0;

  async function start(question: string) {
    setCreating(true);
    setError(null);
    try {
      const conversation = await createConversation();
      upsert(conversation);
      ask(conversation.id, question, 0);
      navigate(`/c/${conversation.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't start a conversation. Try again.");
      setRestore({ text: question, key: Date.now() });
      setCreating(false);
    }
  }

  return (
    <>
      <ViewHeader title="New conversation" />

      <div className="scroll-quiet flex min-h-0 flex-1 flex-col overflow-y-auto">
        <section className="mx-auto flex w-full max-w-[46rem] flex-1 flex-col justify-center px-5 pt-12 pb-[12vh] md:px-6">
          <h2 className="text-display font-semibold tracking-[-0.02em] text-ink">
            Ask about a company policy
          </h2>
          <p className="mt-3 max-w-[34rem] text-lead text-muted">
            Answers come only from the policy documents your role can read, and each
            statement links to the section it came from.
          </p>

          {noAccess ? (
            <div className="mt-6 max-w-[34rem]">
              <Notice tone="warning">
                Your account has no document access, so questions can't be answered. Ask an
                administrator to add an employee, manager, HR or security role.
              </Notice>
            </div>
          ) : (
            <p className="mt-6 text-ui text-muted">
              Searching documents shared with{" "}
              {roles.map((role, index) => (
                <span key={role}>
                  {index > 0 && (index === roles.length - 1 ? " and " : ", ")}
                  <span className="font-medium text-ink-soft">{roleName(role)}</span>
                </span>
              ))}
              .
            </p>
          )}

          {error && (
            <div className="mt-6 max-w-[34rem]">
              <Notice tone="danger">{error}</Notice>
            </div>
          )}
        </section>
      </div>

      <div className="shrink-0 px-3 pt-2 pb-3 md:px-6 md:pb-5">
        <Composer
          onSubmit={noAccess ? undefined : start}
          busy={creating}
          autoFocus={isDesktop}
          restore={restore}
        />
      </div>
    </>
  );
}
